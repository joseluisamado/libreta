from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import frontmatter
from frontmatter import Post

from libreta.errors import PageAlreadyExistsError, PageNotEmptyError, PageNotFoundError
from libreta.models import PageMeta, PageNode, PageRead
from libreta.storage.paths import normalize_page_path, page_to_file


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


def _read_page_sync(content_dir: Path, raw_path: str) -> PageRead:
    page = normalize_page_path(raw_path)
    file = page_to_file(content_dir, page)
    fallback_title = page.parts[-1].replace("-", " ").replace("_", " ").title()
    if not file.exists():
        # Synthesise a directory page: if a directory with this path exists
        # under pages/ but has no `<dir>.md` or `<dir>/index.md`, return an
        # empty-body page so the frontend can still render breadcrumbs and
        # the "In this folder" listing.
        dir_path = content_dir / "pages" / Path(*page.parts)
        if dir_path.is_dir():
            return PageRead(
                path=str(page),
                meta=PageMeta(title=fallback_title),
                body="",
                is_index=True,
            )
        raise PageNotFoundError(raw_path)
    post = frontmatter.load(file)
    return PageRead(
        path=str(page),
        meta=_parse_meta(post.metadata, fallback_title),
        body=post.content,
        is_index=file.name == "index.md",
    )


async def read_page(content_dir: Path, raw_path: str) -> PageRead:
    return await asyncio.to_thread(_read_page_sync, content_dir, raw_path)


def _determine_write_file(
    content_dir: Path, page: PurePosixPath, prefer_index: bool = False
) -> tuple[Path, bool]:
    """Return (target_file, existed_before).

    Prefers ``<page>.md`` if it exists; otherwise falls back to ``<page>/index.md``
    if the directory already exists; otherwise writes to ``<page>.md`` (or
    ``<page>/index.md`` when *prefer_index* is True).
    """
    pages_root = content_dir / "pages"
    direct = pages_root.joinpath(*page.parts).with_suffix(".md")
    indexed = pages_root.joinpath(*page.parts) / "index.md"
    if direct.exists():
        return direct, True
    if indexed.exists():
        return indexed, True
    if prefer_index:
        return indexed, False
    return direct, False


def _write_page_sync(
    content_dir: Path, raw_path: str, body: str, prefer_index: bool = False
) -> tuple[PageRead, str]:
    page = normalize_page_path(raw_path)
    file, existed = _determine_write_file(content_dir, page, prefer_index=prefer_index)
    fallback_title = page.parts[-1].replace("-", " ").replace("_", " ").title()

    # Preserve frontmatter from the existing file if present
    existing_meta: dict[str, Any] = {}
    if existed:
        post = frontmatter.load(file)
        existing_meta = dict(post.metadata)

    # Build metadata: preserve title/created/tags, set updated to now
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

    # Write
    file.parent.mkdir(parents=True, exist_ok=True)
    post = Post(body, **metadata)
    file.write_text(frontmatter.dumps(post), encoding="utf-8")

    verb = "update" if existed else "create"

    result = PageRead(
        path=str(page),
        meta=PageMeta(
            title=str(metadata["title"]),
            created=metadata["created"] if isinstance(metadata["created"], datetime) else now,
            updated=now,
            tags=list(metadata.get("tags", [])),
        ),
        body=body,
        is_index=file.name == "index.md",
    )
    return result, verb


async def write_page(
    content_dir: Path, raw_path: str, body: str, prefer_index: bool = False
) -> tuple[PageRead, str]:
    return await asyncio.to_thread(
        _write_page_sync, content_dir, raw_path, body, prefer_index
    )


def _delete_page_sync(content_dir: Path, raw_path: str) -> str:
    page = normalize_page_path(raw_path)
    file = page_to_file(content_dir, page)

    if file.exists():
        # If this is a directory page backed by index.md, refuse to
        # delete it while other files still live inside the folder.
        if file.name == "index.md":
            parent = file.parent
            pages_root = content_dir / "pages"
            siblings = [p for p in parent.iterdir() if p.name != "index.md"]
            if parent != pages_root and siblings:
                raise PageNotEmptyError(raw_path)
        rel_path = str(file.relative_to(content_dir))
        file.unlink()
        # Clean up the parent directory when it became empty.
        if file.name == "index.md":
            parent = file.parent
            if parent != pages_root and not any(parent.iterdir()):
                parent.rmdir()
        return rel_path

    # No .md file — check whether this is a bare directory (a folder with
    # children but no index.md or <dir>.md).
    dir_path = content_dir / "pages" / Path(*page.parts)
    if dir_path.is_dir():
        if any(dir_path.iterdir()):
            raise PageNotEmptyError(raw_path)
        dir_path.rmdir()
        return str(dir_path.relative_to(content_dir)) + "/"

    raise PageNotFoundError(raw_path)


async def delete_page(content_dir: Path, raw_path: str) -> str:
    return await asyncio.to_thread(_delete_page_sync, content_dir, raw_path)


def _move_page_sync(
    content_dir: Path, old_raw: str, new_raw: str
) -> tuple[str, str, bool]:
    old_page = normalize_page_path(old_raw)
    new_page = normalize_page_path(new_raw)
    old_file = page_to_file(content_dir, old_page)
    if not old_file.exists():
        raise PageNotFoundError(old_raw)

    pages_root = content_dir / "pages"
    is_dir_move = old_file.name == "index.md" and old_file.parent != pages_root

    if is_dir_move:
        target_dir = pages_root.joinpath(*new_page.parts)
        if target_dir.exists():
            raise PageAlreadyExistsError(new_raw)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        old_file.parent.rename(target_dir)
        return (
            str(old_file.parent.relative_to(content_dir)) + "/",
            str(target_dir.relative_to(content_dir)) + "/",
            True,
        )

    target_file = pages_root.joinpath(*new_page.parts).with_suffix(".md")
    if target_file.exists():
        raise PageAlreadyExistsError(new_raw)
    target_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.rename(target_file)
    return (
        str(old_file.relative_to(content_dir)),
        str(target_file.relative_to(content_dir)),
        False,
    )


async def move_page(
    content_dir: Path, old_raw: str, new_raw: str
) -> tuple[str, str, bool]:
    return await asyncio.to_thread(_move_page_sync, content_dir, old_raw, new_raw)


def _walk_tree_sync(content_dir: Path) -> list[PageNode]:
    pages_root = content_dir / "pages"
    if not pages_root.exists():
        return []

    def build(dir_path: Path, url_prefix: str) -> list[PageNode]:
        nodes: list[PageNode] = []
        # collect entries; directories produce subtrees, .md files become leaves
        entries = sorted(dir_path.iterdir(), key=lambda p: p.name.casefold())
        index_md = dir_path / "index.md"
        seen_dirs: set[str] = set()

        for entry in entries:
            if entry.name.startswith("."):
                continue
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
            elif entry.suffix == ".md" and entry.name != "index.md":
                stem = entry.stem
                if stem in seen_dirs:
                    # already represented by the directory node; skip the bare .md
                    continue
                child_url = f"{url_prefix}/{stem}" if url_prefix else stem
                title = _read_title_only(entry, stem)
                nodes.append(
                    PageNode(
                        path=child_url,
                        title=title,
                        is_directory=False,
                        children=[],
                    )
                )
        # if there is an index.md, expose it as the directory's own page (only at root depth)
        # nested directories already carry their index via the `is_directory` flag
        if url_prefix == "" and index_md.exists():
            title = _read_title_only(index_md, "Home")
            nodes.insert(0, PageNode(path="index", title=title, is_directory=False, children=[]))
        return nodes

    return build(pages_root, "")


def _read_title_only(file: Path, fallback: str) -> str:
    try:
        post = frontmatter.load(file)
        title = post.metadata.get("title")
        return str(title) if title else fallback
    except (OSError, ValueError):
        return fallback


async def walk_tree(content_dir: Path) -> list[PageNode]:
    return await asyncio.to_thread(_walk_tree_sync, content_dir)
