from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter
from frontmatter import Post

from libreta.errors import (
    InvalidPathError,
    PageNotFoundError,
    WatchedFileOutsideRootError,
    WatchedFolderNotAccessibleError,
    WatchedLabelNotFoundError,
)
from libreta.models import PageMeta, PageNode, PageRead

logger = logging.getLogger(__name__)

WATCHED_CONFIG_FILENAME = ".meta/watched.json"


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------


def load_watched_config_sync(content_dir: Path) -> list[dict[str, Any]]:
    config_path = content_dir / WATCHED_CONFIG_FILENAME
    if not config_path.exists():
        return []
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [e for e in raw if isinstance(e, dict) and "label" in e and "path" in e]
    except (json.JSONDecodeError, OSError):
        logger.warning("watched config corrupt, treating as empty", exc_info=True)
        return []


async def load_watched_config(content_dir: Path) -> list[dict[str, Any]]:
    return await asyncio.to_thread(load_watched_config_sync, content_dir)


def save_watched_config_sync(content_dir: Path, folders: list[dict[str, Any]]) -> None:
    config_path = content_dir / WATCHED_CONFIG_FILENAME
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(folders, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


async def save_watched_config(content_dir: Path, folders: list[dict[str, Any]]) -> None:
    return await asyncio.to_thread(save_watched_config_sync, content_dir, folders)


# ---------------------------------------------------------------------------
# Path resolution & validation
# ---------------------------------------------------------------------------


def resolve_watched_file_sync(content_dir: Path, label: str, raw_path: str) -> tuple[Path, Path]:
    """Return (watched_root, resolved_file_path) after validating containment."""
    config = load_watched_config_sync(content_dir)
    entry = next((e for e in config if e["label"] == label), None)
    if entry is None:
        raise WatchedLabelNotFoundError(label)

    watched_root = Path(entry["path"]).expanduser().resolve()
    try:
        root_exists = watched_root.exists()
    except OSError as exc:
        raise WatchedFolderNotAccessibleError(str(watched_root)) from exc
    if not root_exists:
        raise WatchedFolderNotAccessibleError(str(watched_root))

    # Validate the raw path segments (empty path = root)
    if raw_path:
        parts = raw_path.split("/")
        for p in parts:
            if not p or p in {".", ".."} or p.startswith("."):
                raise InvalidPathError(f"invalid path segment {p!r} in {raw_path!r}")
            if "\x00" in p:
                raise InvalidPathError("null byte in path")

    candidate = (watched_root / raw_path).resolve() if raw_path else watched_root

    # Path containment check
    try:
        candidate.relative_to(watched_root)
    except ValueError as exc:
        raise WatchedFileOutsideRootError(raw_path) from exc

    return watched_root, candidate


async def resolve_watched_file(content_dir: Path, label: str, raw_path: str) -> tuple[Path, Path]:
    return await asyncio.to_thread(resolve_watched_file_sync, content_dir, label, raw_path)


# ---------------------------------------------------------------------------
# Tree walk for a watched folder
# ---------------------------------------------------------------------------


def _read_title_only(file: Path, fallback: str) -> str:
    try:
        post = frontmatter.load(file)
        title = post.metadata.get("title")
        return str(title) if title else fallback
    except (OSError, ValueError):
        return fallback


def _walk_watched_tree_sync(
    watched_root: Path,
    max_depth: int | None = None,
) -> list[PageNode]:
    try:
        if not watched_root.exists():
            return []
    except OSError:
        logger.warning("cannot access watched root %s", watched_root)
        return []

    def build(dir_path: Path, url_prefix: str, depth: int = 0) -> list[PageNode]:
        nodes: list[PageNode] = []
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError:
            logger.warning("cannot list directory %s", dir_path)
            return nodes

        md_names: dict[str, Path] = {}
        dir_names: dict[str, Path] = {}
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    dir_names[entry.name] = entry
                elif entry.suffix == ".md":
                    md_names[entry.stem] = entry
            except OSError:
                continue

        all_names: set[str] = set()
        all_names.update(md_names.keys())
        all_names.update(dir_names.keys())

        hit_max = max_depth is not None and depth >= max_depth

        for name in sorted(all_names):
            md_file = md_names.get(name)
            sub_dir = dir_names.get(name)
            child_url = f"{url_prefix}/{name}" if url_prefix else name
            has_real_children = bool(sub_dir)

            if hit_max and has_real_children:
                title = (
                    _read_title_only(md_file, name.replace("-", " ").replace("_", " ").title())
                    if md_file
                    else name.replace("-", " ").replace("_", " ").title()
                )
                nodes.append(
                    PageNode(
                        path=child_url,
                        title=title,
                        is_directory=True,
                        children=[],
                        has_more=True,
                    )
                )
            else:
                children = build(sub_dir, child_url, depth + 1) if sub_dir else []
                if md_file:
                    title = _read_title_only(
                        md_file, name.replace("-", " ").replace("_", " ").title()
                    )
                    nodes.append(
                        PageNode(
                            path=child_url,
                            title=title,
                            is_directory=bool(sub_dir),
                            children=children,
                        )
                    )
                else:
                    nodes.append(
                        PageNode(
                            path=child_url,
                            title=name.replace("-", " ").replace("_", " ").title(),
                            is_directory=True,
                            children=children,
                        )
                    )
        return nodes

    return build(watched_root, "")


def _walk_watched_children_sync(watched_root: Path, raw_path: str) -> list[PageNode]:
    """Return immediate children of *raw_path* at max_depth=1."""
    child_dir = (watched_root / raw_path).resolve()
    try:
        child_dir.relative_to(watched_root)
    except ValueError:
        return []
    if not child_dir.is_dir():
        return []
    return _walk_watched_tree_sync(child_dir, max_depth=1)


async def walk_watched_tree(
    watched_root: Path,
    max_depth: int | None = None,
) -> list[PageNode]:
    return await asyncio.to_thread(_walk_watched_tree_sync, watched_root, max_depth)


async def walk_watched_children(watched_root: Path, raw_path: str) -> list[PageNode]:
    return await asyncio.to_thread(_walk_watched_children_sync, watched_root, raw_path)


# ---------------------------------------------------------------------------
# Read & write
# ---------------------------------------------------------------------------


def _parse_meta(raw: dict[str, Any], fallback_title: str) -> PageMeta:
    title = raw.get("title") or fallback_title
    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    return PageMeta(
        title=str(title),
        created=_as_datetime(raw.get("created")),
        updated=_as_datetime(raw.get("updated")),
        tags=[str(t) for t in tags],
    )


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _read_watched_page_sync(watched_root: Path, raw_path: str) -> PageRead:
    """Read a page from a watched folder.

    *raw_path* is the URL path — no .md extension."""
    file = watched_root / raw_path
    fallback_title = file.name.replace("-", " ").replace("_", " ").title()

    try:
        actual = file.with_suffix(".md") if not file.suffix else file
        if actual.exists():
            post = frontmatter.load(actual)
            return PageRead(
                path=raw_path,
                meta=_parse_meta(post.metadata, fallback_title),
                body=post.content,
            )

        # Synthesise empty directory page
        if file.is_dir():
            return PageRead(
                path=raw_path,
                meta=PageMeta(title=fallback_title),
                body="",
            )

        raise PageNotFoundError(raw_path)
    except OSError as exc:
        raise WatchedFolderNotAccessibleError(str(file)) from exc


async def read_watched_page(watched_root: Path, raw_path: str) -> PageRead:
    return await asyncio.to_thread(_read_watched_page_sync, watched_root, raw_path)


def _write_watched_page_sync(watched_root: Path, raw_path: str, body: str) -> tuple[PageRead, str]:
    """Write a page in a watched folder. No git commit."""
    file = watched_root / raw_path
    fallback_title = file.name.replace("-", " ").replace("_", " ").title()

    existing = file.with_suffix(".md") if not file.suffix else file
    existed = existing.exists()

    existing_meta: dict[str, Any] = {}
    if existed:
        try:
            post = frontmatter.load(existing)
            existing_meta = dict(post.metadata)
        except (OSError, ValueError):
            pass

    now = datetime.now(UTC)
    metadata: dict[str, Any] = {
        "title": existing_meta.get("title", fallback_title),
        "updated": now,
    }
    if "created" in existing_meta:
        metadata["created"] = existing_meta["created"]
    else:
        metadata["created"] = now
    if "tags" in existing_meta:
        metadata["tags"] = existing_meta["tags"]

    existing.parent.mkdir(parents=True, exist_ok=True)
    post = Post(body, **metadata)
    existing.write_text(frontmatter.dumps(post), encoding="utf-8")

    verb = "update" if existed else "create"

    result = PageRead(
        path=raw_path,
        meta=PageMeta(
            title=str(metadata["title"]),
            created=metadata["created"] if isinstance(metadata["created"], datetime) else now,
            updated=now,
            tags=list(metadata.get("tags", [])),
        ),
        body=body,
    )
    return result, verb


async def write_watched_page(watched_root: Path, raw_path: str, body: str) -> tuple[PageRead, str]:
    return await asyncio.to_thread(_write_watched_page_sync, watched_root, raw_path, body)


def _create_watched_folder_sync(watched_root: Path, raw_path: str) -> None:
    """Create an empty directory (with .gitkeep) in a watched folder."""
    dir_path = (watched_root / raw_path).resolve()
    try:
        dir_path.relative_to(watched_root)
    except ValueError:
        raise WatchedFileOutsideRootError(raw_path)
    if dir_path.exists():
        raise FileExistsError(str(dir_path))
    dir_path.mkdir(parents=True)
    (dir_path / ".gitkeep").write_text("")


async def create_watched_folder(watched_root: Path, raw_path: str) -> None:
    await asyncio.to_thread(_create_watched_folder_sync, watched_root, raw_path)


def _delete_watched_page_sync(watched_root: Path, raw_path: str) -> None:
    """Delete a page or empty directory from a watched folder."""
    md_file = (watched_root / raw_path).with_suffix(".md")
    dir_path = watched_root / raw_path

    try:
        (watched_root / raw_path).resolve().relative_to(watched_root.resolve())
    except ValueError:
        raise WatchedFileOutsideRootError(raw_path)

    if md_file.is_file():
        sidecar = md_file.parent / f".{md_file.name}"
        md_file.unlink()
        if sidecar.is_dir():
            for f in sidecar.rglob("*"):
                if f.is_file():
                    f.unlink()
            sidecar.rmdir()
    elif dir_path.is_dir():
        gitkeep = dir_path / ".gitkeep"
        if gitkeep.is_file():
            gitkeep.unlink()
        contents = [p for p in dir_path.iterdir() if not p.name.startswith(".")]
        if contents:
            raise OSError(f"Directory not empty: {raw_path}")
        for p in dir_path.iterdir():
            if p.is_file():
                p.unlink()
        dir_path.rmdir()
    else:
        raise PageNotFoundError(raw_path)


async def delete_watched_page(watched_root: Path, raw_path: str) -> None:
    await asyncio.to_thread(_delete_watched_page_sync, watched_root, raw_path)
