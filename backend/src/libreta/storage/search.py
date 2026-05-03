from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from pathlib import Path

import frontmatter

from libreta.storage.paths import normalize_page_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB location & schema
# ---------------------------------------------------------------------------

_DB_SUBDIR = ".libreta"
_DB_NAME = "search.db"


def db_path(content_dir: Path) -> Path:
    return content_dir / _DB_SUBDIR / _DB_NAME


def _connect(content_dir: Path) -> sqlite3.Connection:
    path = db_path(content_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # Enable WAL so reads don't block writes.
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(
            path UNINDEXED,
            title,
            body,
            tags,
            updated UNINDEXED,
            tokenize = 'porter unicode61 remove_diacritics 2'
        );
        CREATE TABLE IF NOT EXISTS pages_meta (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def _page_text(md_file: Path) -> tuple[str, str, str, str]:
    """Return (path, title, body, tags) for a markdown file."""
    try:
        post = frontmatter.load(md_file)
    except Exception:
        return "", "", "", ""

    raw_tags = post.metadata.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = [str(raw_tags)]
    tags = " ".join(str(t) for t in raw_tags)

    title = str(post.metadata.get("title", ""))
    updated = str(post.metadata.get("updated", ""))
    body = post.content

    return title, body, tags, updated


def _upsert_page_sync(conn: sqlite3.Connection, md_file: Path, content_dir: Path) -> None:
    rel = str(md_file.relative_to(content_dir))
    # Strip pages/ prefix and .md suffix to get the API path.
    try:
        page_path = str(normalize_page_path(rel.removeprefix("pages/").removesuffix(".md")))
    except Exception:
        return

    title, body, tags, updated = _page_text(md_file)
    mtime = md_file.stat().st_mtime

    conn.execute("DELETE FROM documents WHERE path = ?", (page_path,))
    conn.execute(
        "INSERT INTO documents(path, title, body, tags, updated) VALUES (?,?,?,?,?)",
        (page_path, title, body, tags, updated),
    )
    conn.execute(
        "INSERT OR REPLACE INTO pages_meta(path, mtime) VALUES (?,?)",
        (page_path, mtime),
    )
    conn.commit()


def _delete_page_sync(conn: sqlite3.Connection, page_path: str) -> None:
    conn.execute("DELETE FROM documents WHERE path = ?", (page_path,))
    conn.execute("DELETE FROM pages_meta WHERE path = ?", (page_path,))
    conn.commit()


def _full_reindex_sync(content_dir: Path) -> int:
    """Drop and rebuild the entire index. Returns number of pages indexed."""
    conn = _connect(content_dir)
    try:
        _ensure_schema(conn)
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM pages_meta")
        conn.commit()

        pages_root = content_dir / "pages"
        count = 0
        for md_file in sorted(pages_root.rglob("*.md")):
            _upsert_page_sync(conn, md_file, content_dir)
            count += 1
        return count
    finally:
        conn.close()


def _incremental_reindex_sync(content_dir: Path) -> int:
    """Index pages whose mtime has changed since last index. Returns number updated."""
    conn = _connect(content_dir)
    try:
        _ensure_schema(conn)
        pages_root = content_dir / "pages"
        updated = 0
        for md_file in sorted(pages_root.rglob("*.md")):
            rel = str(md_file.relative_to(content_dir))
            try:
                page_path = str(normalize_page_path(rel.removeprefix("pages/").removesuffix(".md")))
            except Exception:
                continue
            mtime = md_file.stat().st_mtime
            row = conn.execute(
                "SELECT mtime FROM pages_meta WHERE path = ?", (page_path,)
            ).fetchone()
            if row and abs(row["mtime"] - mtime) < 0.001:
                continue
            _upsert_page_sync(conn, md_file, content_dir)
            updated += 1
        return updated
    finally:
        conn.close()


def _index_single_page_sync(content_dir: Path, md_file: Path) -> None:
    conn = _connect(content_dir)
    try:
        _ensure_schema(conn)
        _upsert_page_sync(conn, md_file, content_dir)
    finally:
        conn.close()


def _remove_page_from_index_sync(content_dir: Path, page_path: str) -> None:
    conn = _connect(content_dir)
    try:
        _ensure_schema(conn)
        _delete_page_sync(conn, page_path)
    finally:
        conn.close()


async def full_reindex(content_dir: Path) -> int:
    return await asyncio.to_thread(_full_reindex_sync, content_dir)


async def incremental_reindex(content_dir: Path) -> int:
    return await asyncio.to_thread(_incremental_reindex_sync, content_dir)


async def index_page(content_dir: Path, md_file: Path) -> None:
    await asyncio.to_thread(_index_single_page_sync, content_dir, md_file)


async def remove_page_from_index(content_dir: Path, page_path: str) -> None:
    await asyncio.to_thread(_remove_page_from_index_sync, content_dir, page_path)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

_TAG_FILTER_RE = re.compile(r"\btag:(\S+)")


def _build_fts_query(q: str) -> str:
    """Rewrite `tag:foo` into an FTS5 column filter `tags:foo`.

    Everything else is passed through verbatim so FTS5 handles phrase
    search (quotes), prefix search (*), boolean operators, etc.
    """
    return _TAG_FILTER_RE.sub(r"tags:\1", q).strip()


def _search_sync(
    content_dir: Path,
    q: str,
    limit: int,
) -> list[dict[str, str]]:
    fts_q = _build_fts_query(q)
    if not fts_q:
        return []

    conn = _connect(content_dir)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """
            SELECT
                path,
                title,
                snippet(documents, 2, '<mark>', '</mark>', '…', 20) AS snippet,
                updated,
                tags
            FROM documents
            WHERE documents MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_q, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError as exc:
        # Bad query syntax — return empty rather than 500.
        logger.warning("FTS5 query error for %r: %s", q, exc)
        return []
    finally:
        conn.close()


async def search(content_dir: Path, q: str, limit: int = 20) -> list[dict[str, str]]:
    return await asyncio.to_thread(_search_sync, content_dir, q, limit)
