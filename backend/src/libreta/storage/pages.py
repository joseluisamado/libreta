from __future__ import annotations

import asyncio
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from libreta.errors import PageAlreadyExistsError, PageNotEmptyError, PageNotFoundError
from libreta.models import PageMeta, PageNode, PageRead
from libreta.storage import pagefile
from libreta.storage.paths import normalize_page_path, page_to_file

logger = logging.getLogger(__name__)


def _pages_root(content_dir: Path) -> Path:
    pages_dir = content_dir / "pages"
    return pages_dir if pages_dir.is_dir() else content_dir


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def _read_page_sync(content_dir: Path, raw_path: str) -> PageRead:
    page = normalize_page_path(raw_path)
    root = _pages_root(content_dir)
    try:
        return pagefile.read_page_file(root, str(page))
    except PageNotFoundError:
        # Synthesise a directory page when a directory exists but has no .md file
        dir_path = root / str(page)
        if dir_path.is_dir():
            fallback = page.parts[-1].replace("-", " ").replace("_", " ").title()
            return PageRead(
                path=str(page),
                meta=PageMeta(title=fallback),
                body="",
            )
        raise


async def read_page(content_dir: Path, raw_path: str) -> PageRead:
    return await asyncio.to_thread(_read_page_sync, content_dir, raw_path)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _write_page_sync(content_dir: Path, raw_path: str, body: str) -> tuple[PageRead, str]:
    page = normalize_page_path(raw_path)
    path_str = str(page)
    root = _pages_root(content_dir)

    file = page_to_file(content_dir, page)
    existed = file.exists()

    extra_meta: dict[str, Any] = {}
    if not existed:
        derived = _derive_tags(content_dir, body, path_str)
        if derived:
            extra_meta["tags"] = derived

    return pagefile.write_page_file(root, path_str, body, extra_meta or None)


async def write_page(content_dir: Path, raw_path: str, body: str) -> tuple[PageRead, str]:
    return await asyncio.to_thread(_write_page_sync, content_dir, raw_path, body)


def _derive_tags(content_dir: Path, body: str, path_str: str) -> list[str]:
    """Return auto-derived tags for a new page, or an empty list."""
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
        fallback_title = path_str.split("/")[-1].replace("-", " ").replace("_", " ").title()
        for t in title_terms({"title": fallback_title}):
            if good_term(t):
                bag.extend([t] * TITLE_BOOST)
        tf = Counter(bag)

        return score_page(tf, df, n_docs)
    except Exception:
        logger.warning("tag derivation failed for %s", path_str, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Delete & move (pages-specific: path normalization + git-committed repo)
# ---------------------------------------------------------------------------


def _delete_page_sync(content_dir: Path, raw_path: str) -> str:
    page = normalize_page_path(raw_path)
    file = page_to_file(content_dir, page)
    pages_root = content_dir / "pages"

    if file.exists():
        rel_path = str(file.relative_to(content_dir))
        file.unlink()
        parent = file.parent
        if parent != pages_root and not any(parent.iterdir()):
            parent.rmdir()
        return rel_path

    # A plain file uploaded into a folder: its path already carries the
    # extension (e.g. "aaa/report.pdf"), so page_to_file's ".md" lookup above
    # misses it. Delete the file as-is.
    base = pages_root if pages_root.is_dir() else content_dir
    raw_file = base.joinpath(*page.parts)
    if raw_file.is_file():
        rel_path = str(raw_file.relative_to(content_dir))
        raw_file.unlink()
        parent = raw_file.parent
        if parent != pages_root and parent != content_dir and not any(parent.iterdir()):
            parent.rmdir()
        return rel_path

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


# ---------------------------------------------------------------------------
# Tree walk
# ---------------------------------------------------------------------------


async def walk_tree(content_dir: Path) -> list[PageNode]:
    return await asyncio.to_thread(pagefile.walk_tree, _pages_root(content_dir))
