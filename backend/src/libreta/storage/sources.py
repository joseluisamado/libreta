"""Git-source storage layer.

Each git source is a remote git repository that Libreta clones to a local
working tree under <repos_dir>/<source_id>/.  Libreta commits writes into the
local clone and pushes asynchronously.

Config is persisted in <content_dir>/.meta/sources.json so it lives alongside
the watched-folder config and respects R2 (filesystem is the source of truth).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pygit2

from libreta.errors import (
    GitSourceAlreadyExistsError,
    GitSourceCloneError,
    GitSourceNotFoundError,
    InvalidPathError,
)
from libreta.models import (
    GitSourceCreate,
    GitSourceResponse,
    GitSourceUpdate,
    OtherFile,
    PageNode,
    PageRead,
)
from libreta.storage import gitea_servers, pagefile
from libreta.storage.ssh import make_callbacks

logger = logging.getLogger(__name__)

# Per-source asyncio write locks.  Keyed by source id.
_locks: dict[str, asyncio.Lock] = {}

# Protects the load-modify-save cycle on sources.json.
_config_lock = threading.Lock()


def _get_lock(source_id: str) -> asyncio.Lock:
    if source_id not in _locks:
        _locks[source_id] = asyncio.Lock()
    return _locks[source_id]


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------


def _config_path(content_dir: Path) -> Path:
    return content_dir / ".meta" / "sources.json"


def load_sources_sync(content_dir: Path) -> list[dict[str, Any]]:
    path = _config_path(content_dir)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return raw
    except (json.JSONDecodeError, OSError):
        logger.warning("sources config corrupt, treating as empty", exc_info=True)
    return []


async def load_sources(content_dir: Path) -> list[dict[str, Any]]:
    return await asyncio.to_thread(load_sources_sync, content_dir)


def save_sources_sync(content_dir: Path, sources: list[dict[str, Any]]) -> None:
    path = _config_path(content_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(sources, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)  # atomic rename — readers never see a partial file


async def save_sources(content_dir: Path, sources: list[dict[str, Any]]) -> None:
    await asyncio.to_thread(save_sources_sync, content_dir, sources)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _local_path(repos_dir: Path, source_id: str) -> Path:
    # source_id arrives from URL path params on read endpoints — enforce the
    # same shape we require at create time, so a request like
    # /api/v1/sources/../assets/... cannot escape the repos directory.
    if not _SOURCE_ID_RE.match(source_id):
        raise InvalidPathError(f"invalid source id: {source_id!r}")
    return repos_dir / source_id


def _pending_count_sync(local: Path, branch: str) -> int:
    """How many local commits are ahead of ``origin/<branch>``.

    Returns 0 when not cloned, when the remote-tracking ref is missing, or
    when local matches remote. Errors are swallowed (treated as 0) — this is
    a best-effort UI hint, not a correctness gate.
    """
    if not (local / ".git").exists():
        return 0
    try:
        repo = _open_repo(local)
        head = repo.head.target
        remote_ref = f"refs/remotes/origin/{branch}"
        if remote_ref not in repo.references:
            return 0
        remote_oid = repo.references[remote_ref].target
        ahead, _behind = repo.ahead_behind(head, remote_oid)
    except (pygit2.GitError, KeyError, ValueError):
        return 0
    return int(ahead)


def _entry_to_response(entry: dict[str, Any], repos_dir: Path) -> GitSourceResponse:
    local = _local_path(repos_dir, entry["id"])
    cloned = (local / ".git").exists()
    last_sync: datetime | None = None
    raw_ts = entry.get("last_synced_at")
    if raw_ts:
        with contextlib.suppress(ValueError):
            last_sync = datetime.fromisoformat(str(raw_ts))
    branch = entry.get("branch", "main")
    return GitSourceResponse(
        id=entry["id"],
        label=entry["label"],
        remote_url=entry["remote_url"],
        branch=branch,
        ssh_key_id=entry.get("ssh_key_id"),
        http_username=entry.get("http_username"),
        gitea_server_id=entry.get("gitea_server_id"),
        sync_interval_minutes=entry.get("sync_interval_minutes", 15),
        local_path=str(local),
        cloned=cloned,
        last_synced_at=last_sync,
        last_sync_error=entry.get("last_sync_error"),
        pending_count=_pending_count_sync(local, branch),
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_sources_sync(content_dir: Path, repos_dir: Path) -> list[GitSourceResponse]:
    return [_entry_to_response(e, repos_dir) for e in load_sources_sync(content_dir)]


async def list_sources(content_dir: Path, repos_dir: Path) -> list[GitSourceResponse]:
    return await asyncio.to_thread(list_sources_sync, content_dir, repos_dir)


def add_source_sync(
    content_dir: Path,
    repos_dir: Path,
    body: GitSourceCreate,
) -> GitSourceResponse:
    with _config_lock:
        sources = load_sources_sync(content_dir)
        if any(s["id"] == body.id for s in sources):
            raise GitSourceAlreadyExistsError(f"source id {body.id!r} already exists")
        entry: dict[str, Any] = {
            "id": body.id,
            "label": body.label,
            "remote_url": body.remote_url,
            "branch": body.branch,
            "ssh_key_id": body.ssh_key_id,
            "http_username": body.http_username,
            "http_password": body.http_password,
            "gitea_server_id": body.gitea_server_id,
            "sync_interval_minutes": body.sync_interval_minutes,
            "last_synced_at": None,
            "last_sync_error": None,
        }
        sources.append(entry)
        save_sources_sync(content_dir, sources)
    return _entry_to_response(entry, repos_dir)


async def add_source(
    content_dir: Path,
    repos_dir: Path,
    body: GitSourceCreate,
) -> GitSourceResponse:
    return await asyncio.to_thread(add_source_sync, content_dir, repos_dir, body)


def update_source_sync(
    content_dir: Path,
    repos_dir: Path,
    source_id: str,
    body: GitSourceUpdate,
) -> GitSourceResponse:
    with _config_lock:
        sources = load_sources_sync(content_dir)
        idx = next((i for i, s in enumerate(sources) if s["id"] == source_id), None)
        if idx is None:
            raise GitSourceNotFoundError(source_id)
        entry = sources[idx]
        if body.label is not None:
            entry["label"] = body.label
        if body.branch is not None:
            entry["branch"] = body.branch
        if body.ssh_key_id is not None:
            entry["ssh_key_id"] = body.ssh_key_id
        if body.http_username is not None:
            entry["http_username"] = body.http_username
        if body.http_password is not None:
            entry["http_password"] = body.http_password
        if body.sync_interval_minutes is not None:
            entry["sync_interval_minutes"] = body.sync_interval_minutes
        sources[idx] = entry
        save_sources_sync(content_dir, sources)
    return _entry_to_response(entry, repos_dir)


async def update_source(
    content_dir: Path,
    repos_dir: Path,
    source_id: str,
    body: GitSourceUpdate,
) -> GitSourceResponse:
    return await asyncio.to_thread(update_source_sync, content_dir, repos_dir, source_id, body)


def remove_source_sync(content_dir: Path, source_id: str) -> None:
    with _config_lock:
        sources = load_sources_sync(content_dir)
        if not any(s["id"] == source_id for s in sources):
            raise GitSourceNotFoundError(source_id)
        save_sources_sync(content_dir, [s for s in sources if s["id"] != source_id])
    _locks.pop(source_id, None)


async def remove_source(content_dir: Path, source_id: str) -> None:
    await asyncio.to_thread(remove_source_sync, content_dir, source_id)


def record_sync_result_sync(
    content_dir: Path,
    source_id: str,
    error: str | None,
) -> None:
    with _config_lock:
        sources = load_sources_sync(content_dir)
        for s in sources:
            if s["id"] == source_id:
                s["last_synced_at"] = datetime.now(UTC).isoformat()
                s["last_sync_error"] = error
        save_sources_sync(content_dir, sources)


async def record_sync_result(
    content_dir: Path,
    source_id: str,
    error: str | None,
) -> None:
    await asyncio.to_thread(record_sync_result_sync, content_dir, source_id, error)


# ---------------------------------------------------------------------------
# Git operations (blocking, wrapped with asyncio.to_thread at call sites)
# ---------------------------------------------------------------------------


def _resolve_http_auth(
    entry: dict[str, Any],
    gitea_servers_dir: Path,
) -> tuple[str | None, str | None]:
    """Return the (username, password) to use for HTTPS git auth.

    When the source references a Gitea server, the credentials come from that
    server's store (so a rotated token applies to every source at once).
    Otherwise the per-source http_username/http_password are used. A failure
    to load server credentials is non-fatal here: it degrades to no HTTP auth,
    and the git op surfaces the resulting error normally.
    """
    server_id = entry.get("gitea_server_id")
    if server_id:
        try:
            return gitea_servers.load_credentials_sync(gitea_servers_dir, server_id)
        except Exception:
            logger.warning(
                "source %s: cannot load gitea server %s credentials",
                entry.get("id"),
                server_id,
                exc_info=True,
            )
            return None, None
    return entry.get("http_username"), entry.get("http_password")


def _open_repo(local: Path) -> pygit2.Repository:
    return pygit2.Repository(str(local))


def clone_source_sync(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    entry: dict[str, Any],
) -> None:
    source_id: str = entry["id"]
    remote_url: str = entry["remote_url"]
    branch: str = entry.get("branch", "main")
    key_id: str | None = entry.get("ssh_key_id")
    http_username, http_password = _resolve_http_auth(entry, gitea_servers_dir)
    local = _local_path(repos_dir, source_id)

    if (local / ".git").exists():
        return  # already cloned

    callbacks = make_callbacks(ssh_keys_dir, key_id, http_username, http_password)
    try:
        local.mkdir(parents=True, exist_ok=True)
        pygit2.clone_repository(
            remote_url,
            str(local),
            checkout_branch=branch,
            callbacks=callbacks,
        )
        logger.info("cloned %s -> %s", remote_url, local)
    except pygit2.GitError as exc:
        raise GitSourceCloneError(f"clone failed for {source_id}: {exc}") from exc


async def clone_source(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    entry: dict[str, Any],
) -> None:
    await asyncio.to_thread(clone_source_sync, repos_dir, ssh_keys_dir, gitea_servers_dir, entry)


def fetch_and_ff_sync(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    entry: dict[str, Any],
) -> None:
    """Fetch from remote and fast-forward the local branch if clean."""
    source_id: str = entry["id"]
    branch: str = entry.get("branch", "main")
    key_id: str | None = entry.get("ssh_key_id")
    http_username, http_password = _resolve_http_auth(entry, gitea_servers_dir)
    local = _local_path(repos_dir, source_id)

    if not (local / ".git").exists():
        clone_source_sync(repos_dir, ssh_keys_dir, gitea_servers_dir, entry)
        return

    callbacks = make_callbacks(ssh_keys_dir, key_id, http_username, http_password)
    repo = _open_repo(local)

    remote = repo.remotes["origin"]
    remote.fetch(callbacks=callbacks)

    remote_ref = f"refs/remotes/origin/{branch}"
    try:
        remote_commit = repo.lookup_reference(remote_ref).peel(pygit2.Commit)
    except (KeyError, pygit2.GitError):
        logger.warning("source %s: remote ref %s not found after fetch", source_id, remote_ref)
        return

    local_ref_name = f"refs/heads/{branch}"
    try:
        local_ref = repo.lookup_reference(local_ref_name)
        local_commit = local_ref.peel(pygit2.Commit)
    except (KeyError, pygit2.GitError):
        # Branch doesn't exist locally yet — create it
        repo.create_reference(local_ref_name, remote_commit.id)
        repo.checkout(local_ref_name)
        return

    # Only fast-forward
    base = repo.merge_base(local_commit.id, remote_commit.id)
    if base == remote_commit.id:
        return  # Already up to date or remote is behind
    if base != local_commit.id:
        logger.warning("source %s: diverged from remote, manual merge needed", source_id)
        return

    # Materialise the remote tree into the index + working tree FIRST, then
    # advance the ref. Order matters: checkout_tree(<target>) diffs the target
    # against the current HEAD/workdir and writes the files that differ. The
    # old code did set_target() first and then checkout_head(), which diffs the
    # *already-advanced* HEAD against the workdir — for purely-added paths that
    # comparison can resolve to "nothing to do", silently leaving new files out
    # of the index and working tree (git status: INDEX_DELETED) while the ref
    # still moved. checkout_tree against the explicit target avoids that.
    #
    # SAFE strategy lets libgit2 itself be the dirty-check: if any tracked file
    # in the FF diff has uncommitted local *modifications*, the checkout aborts
    # without touching anything. This avoids a pre-flight full-tree scan (which
    # on slow-storage hosts hashed every tracked file's contents).
    #
    # RECREATE_MISSING is essential here. Without it, SAFE treats a tracked file
    # that is missing from the working tree as a deliberate local deletion and
    # skips it — so it never gets written. The old code (set_target + then
    # checkout_head) could leave new files in HEAD but absent from the index and
    # working tree (git status: INDEX_DELETED); a plain SAFE checkout then sees
    # those paths as "locally deleted, don't touch" and the repo stays stuck on
    # every subsequent sync. RECREATE_MISSING makes the fast-forward restore
    # files that should exist at the target commit, while SAFE still protects
    # genuine uncommitted edits to existing files.
    strategy = pygit2.enums.CheckoutStrategy.SAFE | pygit2.enums.CheckoutStrategy.RECREATE_MISSING
    try:
        repo.checkout_tree(remote_commit.tree, strategy=strategy)  # type: ignore[no-untyped-call]
    except pygit2.GitError as exc:
        logger.warning("source %s: cannot fast-forward, local changes in path: %s", source_id, exc)
        return
    # Only advance the ref once the working tree + index reflect the new commit.
    local_ref.set_target(remote_commit.id)
    logger.info("source %s: fast-forwarded to %s", source_id, str(remote_commit.id)[:7])


async def fetch_and_ff(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    entry: dict[str, Any],
) -> None:
    await asyncio.to_thread(fetch_and_ff_sync, repos_dir, ssh_keys_dir, gitea_servers_dir, entry)


def push_sync(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    entry: dict[str, Any],
) -> None:
    # Libreta commits on every page write, so a push only ships commits already
    # in HEAD. Files edited outside Libreta are the user's responsibility to
    # commit. Scanning the working tree for stragglers used to cost a full
    # SHA-1 pass over every file on each push.
    source_id: str = entry["id"]
    branch: str = entry.get("branch", "main")
    key_id: str | None = entry.get("ssh_key_id")
    http_username, http_password = _resolve_http_auth(entry, gitea_servers_dir)
    local = _local_path(repos_dir, source_id)

    if not (local / ".git").exists():
        logger.warning("source %s: push requested but not cloned yet", source_id)
        return

    repo = _open_repo(local)

    callbacks = make_callbacks(ssh_keys_dir, key_id, http_username, http_password)
    remote = repo.remotes["origin"]
    refspec = f"refs/heads/{branch}:refs/heads/{branch}"
    remote.push([refspec], callbacks=callbacks)
    logger.info("source %s: pushed branch %s", source_id, branch)


async def push_source(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    entry: dict[str, Any],
) -> None:
    await asyncio.to_thread(push_sync, repos_dir, ssh_keys_dir, gitea_servers_dir, entry)


# ---------------------------------------------------------------------------
# "Pending push" inspection
# ---------------------------------------------------------------------------


def _changed_md_paths(commit: pygit2.Commit, parent: pygit2.Commit | None) -> list[str]:
    """Return the .md page paths touched by *commit* relative to *parent*.

    For a root commit (no parent), every file in the tree counts as added.
    Non-markdown changes (assets, .gitkeep, etc.) are filtered — the popup
    shows "changed pages," not raw file paths.
    """
    diff = (
        commit.tree.diff_to_tree(parent.tree, swap=True)
        if parent is not None
        else commit.tree.diff_to_tree(swap=True)
    )
    out: set[str] = set()
    for delta in diff.deltas:
        for path in (delta.new_file.path, delta.old_file.path):
            if path and path.endswith(".md"):
                # Pages live as `<path>.md`; the wiki addresses them without
                # the .md suffix and without any leading directory wrapping.
                out.add(path[:-3])
    return sorted(out)


def list_pending_sync(repos_dir: Path, source_id: str, branch: str) -> list[dict[str, Any]]:
    local = _local_path(repos_dir, source_id)
    if not (local / ".git").exists():
        return []
    try:
        repo = _open_repo(local)
    except pygit2.GitError:
        return []
    head = repo.head.target
    remote_ref = f"refs/remotes/origin/{branch}"
    stop_at: str | None = None
    if remote_ref in repo.references:
        stop_at = str(repo.references[remote_ref].target)

    out: list[dict[str, Any]] = []
    for commit in repo.walk(head, pygit2.enums.SortMode.TOPOLOGICAL):
        if stop_at is not None and str(commit.id) == stop_at:
            break
        parent = commit.parents[0] if commit.parents else None
        out.append(
            {
                "sha": str(commit.id)[:7],
                "message": commit.message.splitlines()[0] if commit.message else "",
                "author": commit.author.name,
                "timestamp": datetime.fromtimestamp(commit.commit_time, tz=UTC),
                "paths": _changed_md_paths(commit, parent),
            }
        )
    return out


async def list_pending(repos_dir: Path, source_id: str, branch: str) -> list[dict[str, Any]]:
    return await asyncio.to_thread(list_pending_sync, repos_dir, source_id, branch)


# ---------------------------------------------------------------------------
# Commit helper for this source
# ---------------------------------------------------------------------------


def _commit_sync(
    repo: pygit2.Repository,
    rel_paths: list[str],
    message: str,
) -> None:
    index = repo.index
    index.read()
    for p in rel_paths:
        index.add(p)
    index.write()
    tree = index.write_tree()
    try:
        parents = [repo.head.target]
    except (pygit2.GitError, KeyError):
        parents = []
    sig = pygit2.Signature("Libreta", "libreta@localhost")
    repo.create_commit("HEAD", sig, sig, message, tree, parents)


# ---------------------------------------------------------------------------
# Path validation for source page routes (rejects hidden segments)
# ---------------------------------------------------------------------------


def _validate_source_path(raw_path: str) -> None:
    pagefile.validate_path_segments(raw_path)
    for part in raw_path.split("/"):
        if part.startswith("."):
            raise InvalidPathError(f"invalid path segment {part!r}")


# ---------------------------------------------------------------------------
# Tree walk (delegates to pagefile)
# ---------------------------------------------------------------------------


async def walk_source_tree(
    repos_dir: Path,
    source_id: str,
    max_depth: int | None = None,
) -> list[PageNode]:
    return await asyncio.to_thread(pagefile.walk_tree, _local_path(repos_dir, source_id), max_depth)


async def walk_source_children(
    repos_dir: Path,
    source_id: str,
    raw_path: str,
) -> tuple[list[PageNode], list[OtherFile]]:
    local = _local_path(repos_dir, source_id)
    return await asyncio.to_thread(pagefile.walk_children, local, raw_path)


# ---------------------------------------------------------------------------
# Read page (delegates to pagefile)
# ---------------------------------------------------------------------------


async def read_source_page(repos_dir: Path, source_id: str, raw_path: str) -> PageRead:
    _validate_source_path(raw_path)
    local = _local_path(repos_dir, source_id)
    return await asyncio.to_thread(pagefile.read_page_file, local, raw_path)


# ---------------------------------------------------------------------------
# Write page (delegates to pagefile, then commits locally)
# ---------------------------------------------------------------------------


async def write_source_page(
    repos_dir: Path,
    ssh_keys_dir: Path,
    content_dir: Path,
    source_id: str,
    raw_path: str,
    body: str,
) -> PageRead:
    _validate_source_path(raw_path)
    local = _local_path(repos_dir, source_id)
    async with _get_lock(source_id):
        result, _ = await asyncio.to_thread(pagefile.write_page_file, local, raw_path, body)
        existing = (
            (local / raw_path).with_suffix(".md")
            if not Path(raw_path).suffix
            else (local / raw_path)
        )
        repo = _open_repo(local)
        rel = str(existing.relative_to(local))
        _commit_sync(repo, [rel], f"update {rel}")
    return result
