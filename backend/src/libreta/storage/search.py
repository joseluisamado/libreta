from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from pathlib import Path

import frontmatter
import pygit2

from libreta.storage.paths import normalize_page_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB location & schema
# ---------------------------------------------------------------------------

_DB_SUBDIR = ".libreta"
_DB_NAME = "search.db"


def db_path(meta_dir: Path) -> Path:
    return meta_dir / _DB_SUBDIR / _DB_NAME


def _connect(meta_dir: Path) -> sqlite3.Connection:
    path = db_path(meta_dir)
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
        CREATE TABLE IF NOT EXISTS sources_meta (
            source_id TEXT PRIMARY KEY,
            indexed_head TEXT NOT NULL
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


def _upsert_page_sync(
    conn: sqlite3.Connection,
    md_file: Path,
    pages_root: Path,
    source_id: str,
) -> None:
    rel = str(md_file.relative_to(pages_root))
    # The path is relative to the pages root; strip .md suffix.
    try:
        page_path = str(normalize_page_path(rel.removesuffix(".md")))
    except Exception:
        return

    # Store source-qualified key: source_id:page_path
    key = f"{source_id}:{page_path}"

    title, body, tags, updated = _page_text(md_file)
    mtime = md_file.stat().st_mtime

    conn.execute("DELETE FROM documents WHERE path = ?", (key,))
    conn.execute(
        "INSERT INTO documents(path, title, body, tags, updated) VALUES (?,?,?,?,?)",
        (key, title, body, tags, updated),
    )
    conn.execute(
        "INSERT OR REPLACE INTO pages_meta(path, mtime) VALUES (?,?)",
        (key, mtime),
    )
    conn.commit()


def _walk_source_pages(repos_dir: Path, source_id: str) -> tuple[Path, list[Path]]:
    """Return (pages_root, [md_file, ...]) for a git source."""
    local = repos_dir / source_id
    md_files = sorted(
        p
        for p in local.rglob("*.md")
        if p.is_file()
        and not p.name.startswith(".")
        and not any(part.startswith(".") for part in p.relative_to(local).parts)
    )
    return local, md_files


def _delete_page_sync(conn: sqlite3.Connection, page_path: str) -> None:
    conn.execute("DELETE FROM documents WHERE path = ?", (page_path,))
    conn.execute("DELETE FROM pages_meta WHERE path = ?", (page_path,))
    conn.commit()


def _full_reindex_sync(meta_dir: Path, repos_dir: Path) -> int:
    """Drop and rebuild the entire index across all git sources."""
    conn = _connect(meta_dir)
    try:
        _ensure_schema(conn)
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM pages_meta")
        conn.commit()

        count = 0
        conn.execute("DELETE FROM sources_meta")
        conn.commit()
        for source_id in _list_source_ids(repos_dir):
            pages_root, md_files = _walk_source_pages(repos_dir, source_id)
            for md_file in md_files:
                _upsert_page_sync(conn, md_file, pages_root, source_id)
                count += 1
            head = _source_head(repos_dir, source_id)
            if head is not None:
                _record_indexed_head(conn, source_id, head)
        return count
    finally:
        conn.close()


def _list_source_ids(repos_dir: Path) -> list[str]:
    """List source IDs from the repos directory."""
    if not repos_dir.is_dir():
        return []
    # Skip dot-prefixed dirs: archived clones (.<id>_<ts>, left by an
    # archive-on-delete) keep a .git but are not live sources.
    return sorted(
        d.name
        for d in repos_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / ".git").is_dir()
    )


def _source_head(repos_dir: Path, source_id: str) -> str | None:
    """Return the current HEAD oid as hex for a source, or None on failure."""
    try:
        repo = pygit2.Repository(str(repos_dir / source_id))
        return str(repo.head.target)
    except (pygit2.GitError, KeyError):
        return None


def _changed_md_between(
    repo: pygit2.Repository,
    old_head: str,
    new_head: str,
) -> tuple[set[str], set[str]] | None:
    """Return (changed_or_added, removed) .md paths between two commits.

    Paths are relative to the repo root, with the .md suffix intact. Returns
    None if either commit cannot be resolved (e.g., history rewritten),
    signaling the caller to fall back to a full walk.
    """
    try:
        old_obj = repo.get(old_head)
        new_obj = repo.get(new_head)
        if old_obj is None or new_obj is None:
            return None
        old_tree = old_obj.peel(pygit2.Tree)
        new_tree = new_obj.peel(pygit2.Tree)
    except (pygit2.GitError, AttributeError, KeyError):
        return None
    diff = old_tree.diff_to_tree(new_tree)
    changed: set[str] = set()
    removed: set[str] = set()
    for delta in diff.deltas:
        new_path = delta.new_file.path
        old_path = delta.old_file.path
        if new_path and new_path.endswith(".md"):
            # status: ADDED / MODIFIED / RENAMED (new side) / COPIED
            changed.add(new_path)
        if old_path and old_path.endswith(".md") and old_path != new_path:
            # File at old_path is no longer at that path in new tree
            removed.add(old_path)
    return changed, removed


def _incremental_reindex_sync(meta_dir: Path, repos_dir: Path) -> int:
    """Reindex pages that changed since the last run.

    Fast path: when a source's HEAD hasn't moved since the last index, skip
    it entirely. When HEAD moved, ask git for the diff and only touch the
    files that actually changed. Falls back to the original mtime-based scan
    for sources without recorded HEAD (first run after upgrade) or when the
    diff can't be computed.
    """
    conn = _connect(meta_dir)
    try:
        _ensure_schema(conn)
        updated = 0
        for source_id in _list_source_ids(repos_dir):
            current_head = _source_head(repos_dir, source_id)
            row = conn.execute(
                "SELECT indexed_head FROM sources_meta WHERE source_id = ?", (source_id,)
            ).fetchone()
            indexed_head = row["indexed_head"] if row else None

            if current_head is not None and current_head == indexed_head:
                continue  # nothing changed in this repo since we last indexed

            pages_root = repos_dir / source_id

            if current_head is not None and indexed_head is not None:
                try:
                    repo = pygit2.Repository(str(pages_root))
                    diff_result = _changed_md_between(repo, indexed_head, current_head)
                except pygit2.GitError:
                    diff_result = None

                if diff_result is not None:
                    changed, removed = diff_result
                    for rel in changed:
                        md_file = pages_root / rel
                        if md_file.is_file():
                            _upsert_page_sync(conn, md_file, pages_root, source_id)
                            updated += 1
                    for rel in removed:
                        try:
                            page_path = str(normalize_page_path(rel.removesuffix(".md")))
                        except Exception:
                            continue
                        _delete_page_sync(conn, f"{source_id}:{page_path}")
                    _record_indexed_head(conn, source_id, current_head)
                    continue

            # Fallback: walk every .md and compare mtimes.
            _, md_files = _walk_source_pages(repos_dir, source_id)
            for md_file in md_files:
                rel = str(md_file.relative_to(pages_root))
                try:
                    page_path = str(normalize_page_path(rel.removesuffix(".md")))
                except Exception:
                    continue
                key = f"{source_id}:{page_path}"
                mtime = md_file.stat().st_mtime
                row = conn.execute("SELECT mtime FROM pages_meta WHERE path = ?", (key,)).fetchone()
                if row and abs(row["mtime"] - mtime) < 0.001:
                    continue
                _upsert_page_sync(conn, md_file, pages_root, source_id)
                updated += 1
            if current_head is not None:
                _record_indexed_head(conn, source_id, current_head)
        return updated
    finally:
        conn.close()


def _record_indexed_head(conn: sqlite3.Connection, source_id: str, head: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO sources_meta(source_id, indexed_head) VALUES (?, ?)",
        (source_id, head),
    )
    conn.commit()


async def full_reindex(meta_dir: Path, repos_dir: Path) -> int:
    return await asyncio.to_thread(_full_reindex_sync, meta_dir, repos_dir)


async def incremental_reindex(meta_dir: Path, repos_dir: Path) -> int:
    return await asyncio.to_thread(_incremental_reindex_sync, meta_dir, repos_dir)


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
    meta_dir: Path,
    q: str,
    limit: int,
) -> list[dict[str, str]]:
    fts_q = _build_fts_query(q)
    if not fts_q:
        return []

    conn = _connect(meta_dir)
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


async def search(meta_dir: Path, q: str, limit: int = 20) -> list[dict[str, str]]:
    return await asyncio.to_thread(_search_sync, meta_dir, q, limit)
