from __future__ import annotations

import asyncio
import contextlib
import difflib
from datetime import UTC, datetime
from pathlib import Path

import pygit2

from libreta.errors import ContentRepoUnavailableError, PageNotFoundError
from libreta.models import DiffEntry, HistoryEntry

_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def open_repo(content_dir: Path) -> pygit2.Repository:
    try:
        return pygit2.Repository(str(content_dir))
    except (pygit2.GitError, OSError) as exc:
        raise ContentRepoUnavailableError(
            f"cannot open content repo at {content_dir}: {exc}"
        ) from exc


def _commit_page_sync(
    repo: pygit2.Repository,
    rel_path: str,
    verb: str,
    author_name: str = "Libreta",
    author_email: str = "libreta@localhost",
) -> None:
    index = repo.index
    index.add(rel_path)
    index.write()

    tree = index.write_tree()

    try:
        head = repo.head
        parents = [head.target]
    except (pygit2.GitError, KeyError):
        # No HEAD yet (e.g. first commit in a fresh repo)
        parents = []

    author = pygit2.Signature(author_name, author_email)
    committer = author
    message = f"{verb} {rel_path}"

    repo.create_commit(
        "HEAD",
        author,
        committer,
        message,
        tree,
        parents,
    )


async def commit_page(
    repo: pygit2.Repository,
    rel_path: str,
    verb: str,
) -> None:
    async with _get_lock():
        await asyncio.to_thread(_commit_page_sync, repo, rel_path, verb)


def _delete_commit_sync(repo: pygit2.Repository, rel_path: str) -> None:
    index = repo.index
    # Directories (paths ending with "/") are not tracked by git, so
    # there is nothing to remove from the index.  The commit records
    # the deletion of the empty directory for history purposes.
    if not rel_path.endswith("/"):
        with contextlib.suppress(KeyError, OSError):
            index.remove(rel_path)
    index.write()

    tree = index.write_tree()

    try:
        head = repo.head
        parents = [head.target]
    except (pygit2.GitError, KeyError):
        parents = []

    author = pygit2.Signature("Libreta", "libreta@localhost")
    committer = author
    message = f"delete {rel_path.rstrip('/')}"

    repo.create_commit("HEAD", author, committer, message, tree, parents)


async def delete_commit(repo: pygit2.Repository, rel_path: str) -> None:
    async with _get_lock():
        await asyncio.to_thread(_delete_commit_sync, repo, rel_path)


def _move_commit_sync(
    repo: pygit2.Repository,
    old_rel: str,
    new_rel: str,
    is_directory_move: bool = False,
) -> None:
    index = repo.index

    if is_directory_move:
        with contextlib.suppress(KeyError):
            index.remove_all([f"{old_rel}*"])
        content_dir = Path(repo.workdir)
        new_path = content_dir / new_rel
        for f in new_path.rglob("*"):
            if f.is_file():
                index.add(str(f.relative_to(content_dir)))
    else:
        with contextlib.suppress(KeyError):
            index.remove(old_rel)
        index.add(new_rel)

    index.write()
    tree = index.write_tree()

    try:
        head = repo.head
        parents = [head.target]
    except (pygit2.GitError, KeyError):
        parents = []

    author = pygit2.Signature("Libreta", "libreta@localhost")
    committer = author
    message = f"rename {old_rel} -> {new_rel}"

    repo.create_commit("HEAD", author, committer, message, tree, parents)


async def move_commit(
    repo: pygit2.Repository,
    old_rel: str,
    new_rel: str,
    is_directory_move: bool = False,
) -> None:
    async with _get_lock():
        await asyncio.to_thread(_move_commit_sync, repo, old_rel, new_rel, is_directory_move)


# ── history ─────────────────────────────────────────────────────────────

MAX_HISTORY = 50


def _affected_paths_for_commit(
    repo: pygit2.Repository, commit: pygit2.Commit, rel_path: str
) -> bool:
    """Return True if *rel_path* was touched in *commit*."""
    if commit.parents:
        parent = commit.parents[0]
        diff = parent.tree.diff_to_tree(commit.tree, context_lines=0)
        for patch in diff:
            if patch is None:
                continue
            if patch.delta.old_file.path == rel_path:
                return True
            if patch.delta.new_file.path == rel_path:
                return True
    else:
        # Root commit — check if the file exists in the tree.
        try:
            commit.tree[rel_path]
            return True
        except KeyError:
            return False
    return False


def _get_file_history_sync(repo: pygit2.Repository, rel_path: str) -> list[HistoryEntry]:
    try:
        head = repo.head
    except (pygit2.GitError, KeyError):
        return []

    entries: list[HistoryEntry] = []
    for commit in repo.walk(head.target, pygit2.enums.SortMode.TIME):
        if _affected_paths_for_commit(repo, commit, rel_path):
            entries.append(
                HistoryEntry(
                    sha=str(commit.id)[:7],
                    message=commit.message.split("\n", 1)[0].strip(),
                    author=commit.author.name,
                    timestamp=datetime.fromtimestamp(commit.author.time, tz=UTC),
                )
            )
        if len(entries) >= MAX_HISTORY:
            break

    return entries


async def get_file_history(repo: pygit2.Repository, rel_path: str) -> list[HistoryEntry]:
    return await asyncio.to_thread(_get_file_history_sync, repo, rel_path)


# ── diff ────────────────────────────────────────────────────────────────


def _resolve_commit(repo: pygit2.Repository, sha: str) -> pygit2.Commit:
    try:
        obj = repo.revparse_single(sha)
    except (KeyError, ValueError, pygit2.GitError) as exc:
        raise PageNotFoundError(f"unknown revision: {sha}") from exc
    peeled = obj.peel(pygit2.Commit)
    if not isinstance(peeled, pygit2.Commit):
        raise PageNotFoundError(f"not a commit: {sha}")
    return peeled


def _blob_text_at(commit: pygit2.Commit, rel_path: str) -> str | None:
    """Return file contents at *rel_path* in *commit*, or None if absent."""
    try:
        entry = commit.tree[rel_path]
    except KeyError:
        return None
    blob = entry.peel(pygit2.Blob)
    if not isinstance(blob, pygit2.Blob):
        return None
    raw = bytes(blob.data)
    return raw.decode("utf-8", errors="replace")


def _get_file_diff_sync(
    repo: pygit2.Repository, rel_path: str, sha_a: str, sha_b: str
) -> DiffEntry:
    commit_a = _resolve_commit(repo, sha_a)
    commit_b = _resolve_commit(repo, sha_b)

    text_a = _blob_text_at(commit_a, rel_path)
    text_b = _blob_text_at(commit_b, rel_path)

    if text_a is None and text_b is None:
        raise PageNotFoundError(f"{rel_path} present in neither {sha_a} nor {sha_b}")

    lines_a = (text_a or "").splitlines(keepends=True)
    lines_b = (text_b or "").splitlines(keepends=True)
    label_a = f"a/{rel_path}" if text_a is not None else "/dev/null"
    label_b = f"b/{rel_path}" if text_b is not None else "/dev/null"
    patch = "".join(difflib.unified_diff(lines_a, lines_b, fromfile=label_a, tofile=label_b, n=3))

    return DiffEntry(
        old_sha=str(commit_a.id)[:7],
        new_sha=str(commit_b.id)[:7],
        old_path=rel_path if text_a is not None else None,
        new_path=rel_path if text_b is not None else None,
        patch=patch,
    )


async def get_file_diff(
    repo: pygit2.Repository, rel_path: str, sha_a: str, sha_b: str
) -> DiffEntry:
    return await asyncio.to_thread(_get_file_diff_sync, repo, rel_path, sha_a, sha_b)
