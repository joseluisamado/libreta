"""Git-source storage layer.

Each git source is a remote git repository that Libreta clones to a local
working tree under <repos_dir>/<source_id>/.  Libreta commits writes into the
local clone and pushes asynchronously.

Config is persisted in <content_dir>/_meta/sources.json so it lives alongside
the watched-folder config and respects R2 (filesystem is the source of truth).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter
import pygit2
from frontmatter import Post

from libreta.errors import (
    GitSourceAlreadyExistsError,
    GitSourceCloneError,
    GitSourceNotFoundError,
    InvalidPathError,
    PageNotFoundError,
)
from libreta.models import (
    GitSourceCreate,
    GitSourceResponse,
    GitSourceUpdate,
    PageMeta,
    PageNode,
    PageRead,
)
from libreta.storage.ssh import make_callbacks

logger = logging.getLogger(__name__)

# Per-source asyncio write locks.  Keyed by source id.
_locks: dict[str, asyncio.Lock] = {}


def _get_lock(source_id: str) -> asyncio.Lock:
    if source_id not in _locks:
        _locks[source_id] = asyncio.Lock()
    return _locks[source_id]


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------


def _config_path(content_dir: Path) -> Path:
    return content_dir / "_meta" / "sources.json"


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
    path.write_text(
        json.dumps(sources, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


async def save_sources(content_dir: Path, sources: list[dict[str, Any]]) -> None:
    await asyncio.to_thread(save_sources_sync, content_dir, sources)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _local_path(repos_dir: Path, source_id: str) -> Path:
    return repos_dir / source_id


def _entry_to_response(entry: dict[str, Any], repos_dir: Path) -> GitSourceResponse:
    local = _local_path(repos_dir, entry["id"])
    cloned = (local / ".git").exists()
    last_sync: datetime | None = None
    raw_ts = entry.get("last_synced_at")
    if raw_ts:
        with contextlib.suppress(ValueError):
            last_sync = datetime.fromisoformat(str(raw_ts))
    return GitSourceResponse(
        id=entry["id"],
        label=entry["label"],
        remote_url=entry["remote_url"],
        branch=entry.get("branch", "main"),
        ssh_key_id=entry.get("ssh_key_id"),
        http_username=entry.get("http_username"),
        sync_interval_minutes=entry.get("sync_interval_minutes", 15),
        local_path=str(local),
        cloned=cloned,
        last_synced_at=last_sync,
        last_sync_error=entry.get("last_sync_error"),
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


def _open_repo(local: Path) -> pygit2.Repository:
    return pygit2.Repository(str(local))


def clone_source_sync(
    repos_dir: Path,
    ssh_keys_dir: Path,
    entry: dict[str, Any],
) -> None:
    source_id: str = entry["id"]
    remote_url: str = entry["remote_url"]
    branch: str = entry.get("branch", "main")
    key_id: str | None = entry.get("ssh_key_id")
    http_username: str | None = entry.get("http_username")
    http_password: str | None = entry.get("http_password")
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
    entry: dict[str, Any],
) -> None:
    await asyncio.to_thread(clone_source_sync, repos_dir, ssh_keys_dir, entry)


def fetch_and_ff_sync(
    repos_dir: Path,
    ssh_keys_dir: Path,
    entry: dict[str, Any],
) -> None:
    """Fetch from remote and fast-forward the local branch if clean."""
    source_id: str = entry["id"]
    branch: str = entry.get("branch", "main")
    key_id: str | None = entry.get("ssh_key_id")
    http_username: str | None = entry.get("http_username")
    http_password: str | None = entry.get("http_password")
    local = _local_path(repos_dir, source_id)

    if not (local / ".git").exists():
        clone_source_sync(repos_dir, ssh_keys_dir, entry)
        return

    callbacks = make_callbacks(ssh_keys_dir, key_id, http_username, http_password)
    repo = _open_repo(local)

    # Check for uncommitted changes
    status = repo.status()
    dirty = any(
        flags
        & (
            pygit2.enums.FileStatus.INDEX_NEW
            | pygit2.enums.FileStatus.INDEX_MODIFIED
            | pygit2.enums.FileStatus.INDEX_DELETED
            | pygit2.enums.FileStatus.WT_MODIFIED
            | pygit2.enums.FileStatus.WT_DELETED
        )
        for flags in status.values()
    )
    if dirty:
        logger.warning("source %s has uncommitted changes, skipping pull", source_id)
        return

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

    local_ref.set_target(remote_commit.id)
    repo.checkout_head(strategy=pygit2.enums.CheckoutStrategy.FORCE)  # type: ignore[no-untyped-call]
    logger.info("source %s: fast-forwarded to %s", source_id, str(remote_commit.id)[:7])


async def fetch_and_ff(
    repos_dir: Path,
    ssh_keys_dir: Path,
    entry: dict[str, Any],
) -> None:
    await asyncio.to_thread(fetch_and_ff_sync, repos_dir, ssh_keys_dir, entry)


def push_sync(
    repos_dir: Path,
    ssh_keys_dir: Path,
    entry: dict[str, Any],
) -> None:
    source_id: str = entry["id"]
    branch: str = entry.get("branch", "main")
    key_id: str | None = entry.get("ssh_key_id")
    http_username: str | None = entry.get("http_username")
    http_password: str | None = entry.get("http_password")
    local = _local_path(repos_dir, source_id)

    if not (local / ".git").exists():
        logger.warning("source %s: push requested but not cloned yet", source_id)
        return

    callbacks = make_callbacks(ssh_keys_dir, key_id, http_username, http_password)
    repo = _open_repo(local)
    remote = repo.remotes["origin"]
    refspec = f"refs/heads/{branch}:refs/heads/{branch}"
    remote.push([refspec], callbacks=callbacks)
    logger.info("source %s: pushed branch %s", source_id, branch)


async def push_source(
    repos_dir: Path,
    ssh_keys_dir: Path,
    entry: dict[str, Any],
) -> None:
    await asyncio.to_thread(push_sync, repos_dir, ssh_keys_dir, entry)


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
# Tree walk (identical logic to watched.py, just applied to the source clone)
# ---------------------------------------------------------------------------


def _read_title_only(file: Path, fallback: str) -> str:
    try:
        post = frontmatter.load(file)
        title = post.metadata.get("title")
        return str(title) if title else fallback
    except (OSError, ValueError):
        return fallback


def _walk_tree_sync(pages_root: Path) -> list[PageNode]:
    if not pages_root.exists():
        return []

    def build(dir_path: Path, url_prefix: str) -> list[PageNode]:
        nodes: list[PageNode] = []
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError:
            return nodes

        md_names: dict[str, Path] = {}
        dir_names: dict[str, Path] = {}
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    dir_names[entry.name] = entry
                elif entry.suffix == ".md":
                    md_names[entry.stem] = entry
            except OSError:
                continue

        all_names: set[str] = set()
        all_names.update(md_names.keys())
        all_names.update(dir_names.keys())

        for name in sorted(all_names):
            md_file = md_names.get(name)
            sub_dir = dir_names.get(name)
            child_url = f"{url_prefix}/{name}" if url_prefix else name
            children = build(sub_dir, child_url) if sub_dir else []
            if md_file:
                title = _read_title_only(md_file, name.replace("-", " ").replace("_", " ").title())
                nodes.append(
                    PageNode(
                        path=child_url,
                        title=title,
                        is_directory=bool(sub_dir),
                        children=children,
                    )
                )
            else:
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


async def walk_source_tree(repos_dir: Path, source_id: str) -> list[PageNode]:
    return await asyncio.to_thread(_walk_tree_sync, _local_path(repos_dir, source_id))


# ---------------------------------------------------------------------------
# Read page
# ---------------------------------------------------------------------------


def _parse_meta(raw: dict[str, Any], fallback_title: str) -> PageMeta:
    title = raw.get("title") or fallback_title
    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    return PageMeta(
        title=str(title),
        created=_as_dt(raw.get("created")),
        updated=_as_dt(raw.get("updated")),
        tags=[str(t) for t in tags],
    )


def _as_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _validate_path_segments(raw_path: str) -> None:
    if not raw_path:
        return
    for part in raw_path.split("/"):
        if not part or part in {".", ".."} or part.startswith("."):
            raise InvalidPathError(f"invalid path segment {part!r}")
        if "\x00" in part:
            raise InvalidPathError("null byte in path")


def _read_page_sync(pages_root: Path, raw_path: str) -> PageRead:
    _validate_path_segments(raw_path)
    file = pages_root / raw_path
    fallback = file.name.replace("-", " ").replace("_", " ").title()

    direct = file.with_suffix(".md") if not file.suffix else file
    if direct.exists():
        post = frontmatter.load(direct)
        return PageRead(
            path=raw_path,
            meta=_parse_meta(post.metadata, fallback),
            body=post.content,
        )

    if file.is_dir():
        return PageRead(
            path=raw_path,
            meta=PageMeta(title=fallback),
            body="",
        )

    raise PageNotFoundError(raw_path)


async def read_source_page(repos_dir: Path, source_id: str, raw_path: str) -> PageRead:
    return await asyncio.to_thread(_read_page_sync, _local_path(repos_dir, source_id), raw_path)


# ---------------------------------------------------------------------------
# Write page (commits locally; caller enqueues push)
# ---------------------------------------------------------------------------


def _write_page_sync(
    local: Path,
    raw_path: str,
    body: str,
) -> tuple[PageRead, str]:
    _validate_path_segments(raw_path)
    file = local / raw_path
    fallback = file.name.replace("-", " ").replace("_", " ").title()

    existing = file.with_suffix(".md") if not file.suffix else file
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
        "title": existing_meta.get("title", fallback),
        "updated": now,
        "created": existing_meta.get("created", now),
    }
    if "tags" in existing_meta:
        metadata["tags"] = existing_meta["tags"]

    existing.parent.mkdir(parents=True, exist_ok=True)
    new_post = Post(body, **metadata)
    existing.write_text(frontmatter.dumps(new_post), encoding="utf-8")

    # git commit
    repo = _open_repo(local)
    rel = str(existing.relative_to(local))
    verb = "update" if existed else "create"
    _commit_sync(repo, [rel], f"{verb} {rel}")

    result = PageRead(
        path=raw_path,
        meta=PageMeta(
            title=str(metadata["title"]),
            created=metadata["created"] if isinstance(metadata["created"], datetime) else now,
            updated=now,
            tags=list(metadata.get("tags", [])),
        ),
        body=body,
    )
    return result, verb


async def write_source_page(
    repos_dir: Path,
    ssh_keys_dir: Path,
    content_dir: Path,
    source_id: str,
    raw_path: str,
    body: str,
) -> PageRead:
    local = _local_path(repos_dir, source_id)
    async with _get_lock(source_id):
        result, _ = await asyncio.to_thread(_write_page_sync, local, raw_path, body)
    return result
