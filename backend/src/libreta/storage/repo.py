from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from pathlib import Path

import pygit2

from libreta.errors import ContentRepoUnavailableError
from libreta.models import HistoryEntry

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
