from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter

from libreta.errors import PageNotFoundError
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
    if not file.exists():
        raise PageNotFoundError(raw_path)
    post = frontmatter.load(file)
    fallback_title = page.parts[-1].replace("-", " ").replace("_", " ").title()
    return PageRead(
        path=str(page),
        meta=_parse_meta(post.metadata, fallback_title),
        body=post.content,
        is_index=file.name == "index.md",
    )


async def read_page(content_dir: Path, raw_path: str) -> PageRead:
    return await asyncio.to_thread(_read_page_sync, content_dir, raw_path)


def _walk_tree_sync(content_dir: Path) -> list[PageNode]:
    pages_root = content_dir / "pages"
    if not pages_root.exists():
        return []

    def build(dir_path: Path, url_prefix: str) -> list[PageNode]:
        nodes: list[PageNode] = []
        # collect entries; directories produce subtrees, .md files become leaves
        entries = sorted(dir_path.iterdir(), key=lambda p: p.name)
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
