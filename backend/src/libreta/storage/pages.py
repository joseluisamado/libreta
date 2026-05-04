from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter
from frontmatter import Post

from libreta.errors import PageAlreadyExistsError, PageNotEmptyError, PageNotFoundError
from libreta.models import PageMeta, PageNode, PageRead
from libreta.storage.paths import normalize_page_path, page_to_file

logger = logging.getLogger(__name__)


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
        # under pages/ but has no `<dir>.md`, return an empty-body page so
        # the frontend can still render breadcrumbs and a child listing.
        dir_path = content_dir / "pages" / Path(*page.parts)
        if dir_path.is_dir():
            return PageRead(
                path=str(page),
                meta=PageMeta(title=fallback_title),
                body="",
            )
        raise PageNotFoundError(raw_path)
    post = frontmatter.load(file)
    return PageRead(
        path=str(page),
        meta=_parse_meta(post.metadata, fallback_title),
        body=post.content,
    )


async def read_page(content_dir: Path, raw_path: str) -> PageRead:
    return await asyncio.to_thread(_read_page_sync, content_dir, raw_path)


def _write_page_sync(content_dir: Path, raw_path: str, body: str) -> tuple[PageRead, str]:
    page = normalize_page_path(raw_path)
    file = page_to_file(content_dir, page)
    fallback_title = page.parts[-1].replace("-", " ").replace("_", " ").title()
    existed = file.exists()

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

    # Derive tags on first save when the page has no tags yet.
    if not existed and not metadata.get("tags"):
        try:
            from libreta.tagging import (
                HEADING_BOOST,
                TITLE_BOOST,
                build_corpus_df,
                good_term,
                heading_terms,
                score_page,
                strip_markup,
                title_terms,
                tokenize,
            )

            df, n_docs = build_corpus_df(content_dir)

            clean_body = strip_markup(body)
            bag: list[str] = []
            bag.extend(t for t in tokenize(clean_body) if good_term(t))
            for t in heading_terms(body):
                if good_term(t):
                    bag.extend([t] * HEADING_BOOST)
            for t in title_terms(metadata):
                if good_term(t):
                    bag.extend([t] * TITLE_BOOST)
            tf = Counter(bag)

            chosen = score_page(tf, df, n_docs)
            if chosen:
                metadata["tags"] = chosen
        except Exception:
            logger.warning("tag derivation failed for %s", raw_path, exc_info=True)

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
    )
    return result, verb


async def write_page(content_dir: Path, raw_path: str, body: str) -> tuple[PageRead, str]:
    return await asyncio.to_thread(_write_page_sync, content_dir, raw_path, body)


def _delete_page_sync(content_dir: Path, raw_path: str) -> str:
    page = normalize_page_path(raw_path)
    file = page_to_file(content_dir, page)

    if file.exists():
        rel_path = str(file.relative_to(content_dir))
        file.unlink()
        # Clean up the parent directory if it became empty.
        parent = file.parent
        pages_root = content_dir / "pages"
        if parent != pages_root and not any(parent.iterdir()):
            parent.rmdir()
        return rel_path

    # No .md file — check whether this is a bare directory (a folder with
    # children but no .md file).
    dir_path = content_dir / "pages" / Path(*page.parts)
    if dir_path.is_dir():
        if any(dir_path.iterdir()):
            raise PageNotEmptyError(raw_path)
        dir_path.rmdir()
        return str(dir_path.relative_to(content_dir)) + "/"

    raise PageNotFoundError(raw_path)


async def delete_page(content_dir: Path, raw_path: str) -> str:
    return await asyncio.to_thread(_delete_page_sync, content_dir, raw_path)


def _move_page_sync(content_dir: Path, old_raw: str, new_raw: str) -> tuple[str, str, bool]:
    old_page = normalize_page_path(old_raw)
    new_page = normalize_page_path(new_raw)
    old_file = page_to_file(content_dir, old_page)
    if not old_file.exists():
        raise PageNotFoundError(old_raw)

    pages_root = content_dir / "pages"
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


async def move_page(content_dir: Path, old_raw: str, new_raw: str) -> tuple[str, str, bool]:
    return await asyncio.to_thread(_move_page_sync, content_dir, old_raw, new_raw)


def _walk_tree_sync(content_dir: Path) -> list[PageNode]:
    pages_root = content_dir / "pages"
    if not pages_root.exists():
        return []

    def build(dir_path: Path, url_prefix: str) -> list[PageNode]:
        nodes: list[PageNode] = []
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError:
            return nodes

        # Partition entries: dot-files are skipped, .md files become pages,
        # directories provide children.
        md_names: dict[str, Path] = {}
        dir_names: dict[str, Path] = {}
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dir_names[entry.name] = entry
            elif entry.suffix == ".md":
                md_names[entry.stem] = entry

        all_names: set[str] = set()
        all_names.update(md_names.keys())
        all_names.update(dir_names.keys())

        for name in sorted(all_names):
            md_file = md_names.get(name)
            sub_dir = dir_names.get(name)
            child_url = f"{url_prefix}/{name}" if url_prefix else name
            children = build(sub_dir, child_url) if sub_dir else []
            if md_file:
                title = _read_title_only(md_file, name)
                nodes.append(
                    PageNode(
                        path=child_url,
                        title=title,
                        is_directory=bool(sub_dir),
                        children=children,
                    )
                )
            else:
                # Directory without a matching .md
                nodes.append(
                    PageNode(
                        path=child_url,
                        title=name.replace("-", " ").replace("_", " ").title(),
                        is_directory=True,
                        children=children,
                    )
                )
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
