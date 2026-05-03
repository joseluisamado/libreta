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

WATCHED_CONFIG_FILENAME = "_meta/watched.json"


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


def _walk_watched_tree_sync(watched_root: Path) -> list[PageNode]:
    try:
        if not watched_root.exists():
            return []
    except OSError:
        logger.warning("cannot access watched root %s", watched_root)
        return []

    def build(dir_path: Path, url_prefix: str) -> list[PageNode]:
        nodes: list[PageNode] = []
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError:
            logger.warning("cannot list directory %s", dir_path)
            return nodes
        seen_dirs: set[str] = set()

        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    child_url = f"{url_prefix}/{entry.name}" if url_prefix else entry.name
                    children = build(entry, child_url)
                    nodes.append(
                        PageNode(
                            path=child_url,
                            title=entry.name.replace("-", " ").replace("_", " ").title(),
                            is_directory=True,
                            children=children,
                        )
                    )
                    seen_dirs.add(entry.name)
                elif entry.suffix == ".md":
                    stem = entry.stem
                    if stem in seen_dirs:
                        continue
                    child_url = f"{url_prefix}/{stem}" if url_prefix else stem
                    title = _read_title_only(
                        entry, stem.replace("-", " ").replace("_", " ").title()
                    )
                    nodes.append(
                        PageNode(
                            path=child_url,
                            title=title,
                            is_directory=False,
                            children=[],
                        )
                    )
            except OSError:
                logger.warning("cannot access entry %s", entry, exc_info=True)
                continue
        return nodes

    return build(watched_root, "")


async def walk_watched_tree(watched_root: Path) -> list[PageNode]:
    return await asyncio.to_thread(_walk_watched_tree_sync, watched_root)


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


def _resolve_md_file(dir_path: Path, name: str) -> Path:
    """Return the actual .md file path for a given page name.

    Prefers ``<name>.md``; falls back to ``<name>/index.md``.
    Always returns a path even if neither exists — the caller checks existence.
    """
    direct = dir_path / f"{name}.md"
    indexed = dir_path / name / "index.md"
    if direct.exists():
        return direct
    if indexed.exists():
        return indexed
    # Default to direct path for writes
    return direct


def _read_watched_page_sync(watched_root: Path, raw_path: str) -> PageRead:
    """Read a page from a watched folder.

    *raw_path* is the URL path — no .md extension."""
    file = watched_root / raw_path
    fallback_title = file.name.replace("-", " ").replace("_", " ").title()

    try:
        # Try to find the actual .md file
        actual = file.with_suffix(".md") if not file.suffix else file
        if actual.exists():
            post = frontmatter.load(actual)
            return PageRead(
                path=raw_path,
                meta=_parse_meta(post.metadata, fallback_title),
                body=post.content,
                is_index=actual.name == "index.md",
            )

        # Check for index.md inside a directory
        dir_index = file / "index.md"
        if dir_index.exists():
            post = frontmatter.load(dir_index)
            return PageRead(
                path=raw_path,
                meta=_parse_meta(post.metadata, fallback_title),
                body=post.content,
                is_index=True,
            )

        # Synthesise empty directory page
        if file.is_dir():
            return PageRead(
                path=raw_path,
                meta=PageMeta(title=fallback_title),
                body="",
                is_index=True,
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

    # Determine the actual file to write (prefer existing, default to .md sibling)
    existing: Path | None = None
    direct = file.with_suffix(".md") if not file.suffix else file
    indexed = file / "index.md"
    if direct.exists():
        existing = direct
    elif indexed.exists():
        existing = indexed
    else:
        existing = direct

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
        is_index=existing.name == "index.md",
    )
    return result, verb


async def write_watched_page(watched_root: Path, raw_path: str, body: str) -> tuple[PageRead, str]:
    return await asyncio.to_thread(_write_watched_page_sync, watched_root, raw_path, body)
