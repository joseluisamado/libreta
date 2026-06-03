"""Background sync service for git sources.

Responsibilities:
- On startup: clone missing sources, fetch+fast-forward existing ones.
- Periodic: re-sync each source according to its sync_interval_minutes.
- Push queue: after a local commit, enqueue a push with exponential backoff.

Designed to run as long-lived asyncio tasks inside the FastAPI lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from libreta.storage.sources import (
    fetch_and_ff,
    load_sources,
    push_sync,
    record_sync_result,
)

logger = logging.getLogger(__name__)

# Maximum retries for push-after-commit
_PUSH_MAX_RETRIES = 3
_PUSH_BASE_DELAY = 5.0  # seconds

# Queue for pending pushes: (source_id,)
_push_queue: asyncio.Queue[str] = asyncio.Queue()


def enqueue_push(source_id: str) -> None:
    """Called after a successful local commit to schedule an async push."""
    _push_queue.put_nowait(source_id)


async def _do_push(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    meta_dir: Path,
    source_id: str,
) -> None:
    sources = await load_sources(meta_dir)
    entry = next((s for s in sources if s["id"] == source_id), None)
    if entry is None:
        logger.warning("push: source %s not found in config, skipping", source_id)
        return

    delay = _PUSH_BASE_DELAY
    for attempt in range(1, _PUSH_MAX_RETRIES + 1):
        try:
            await asyncio.to_thread(push_sync, repos_dir, ssh_keys_dir, gitea_servers_dir, entry)
            await record_sync_result(meta_dir, source_id, None)
            logger.info("push: source %s pushed (attempt %d)", source_id, attempt)
            return
        except Exception as exc:
            logger.warning("push: source %s attempt %d failed: %s", source_id, attempt, exc)
            if attempt < _PUSH_MAX_RETRIES:
                await asyncio.sleep(delay)
                delay *= 2

    error = f"push failed after {_PUSH_MAX_RETRIES} attempts"
    await record_sync_result(meta_dir, source_id, error)


async def push_worker(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    meta_dir: Path,
) -> None:
    """Drain the push queue forever.  Run as a background task."""
    while True:
        source_id = await _push_queue.get()
        try:
            await _do_push(repos_dir, ssh_keys_dir, gitea_servers_dir, meta_dir, source_id)
        except Exception:
            logger.exception("push worker: unhandled error for %s", source_id)
        finally:
            _push_queue.task_done()


async def _sync_one(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    meta_dir: Path,
    entry: dict,  # type: ignore[type-arg]
) -> None:
    source_id: str = entry["id"]
    try:
        await fetch_and_ff(repos_dir, ssh_keys_dir, gitea_servers_dir, entry)
        await record_sync_result(meta_dir, source_id, None)
        logger.info("sync: source %s up to date", source_id)
    except Exception as exc:
        error = str(exc)
        logger.warning("sync: source %s failed: %s", source_id, error)
        await record_sync_result(meta_dir, source_id, error)


_SYNC_PARALLELISM = 2

# Shared across startup_sync and periodic_sync_loop so the two paths cannot
# overlap and double the CPU load right after process start.
_sync_sem: asyncio.Semaphore | None = None


def _get_sync_sem() -> asyncio.Semaphore:
    global _sync_sem
    if _sync_sem is None:
        _sync_sem = asyncio.Semaphore(_SYNC_PARALLELISM)
    return _sync_sem


async def _bounded_sync_one(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    meta_dir: Path,
    entry: dict,  # type: ignore[type-arg]
) -> None:
    async with _get_sync_sem():
        await _sync_one(repos_dir, ssh_keys_dir, gitea_servers_dir, meta_dir, entry)


async def startup_sync(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    meta_dir: Path,
) -> None:
    """Clone missing sources and fetch existing ones at startup.

    Capped at _SYNC_PARALLELISM concurrent syncs. libgit2's fetch (delta
    resolution) is CPU-bound and single-threaded per call, so fanning out
    every source in parallel on a low-core host just pegs all cores and
    increases wall-clock time through contention.
    """
    sources = await load_sources(meta_dir)
    if not sources:
        return
    await asyncio.gather(
        *[
            _bounded_sync_one(repos_dir, ssh_keys_dir, gitea_servers_dir, meta_dir, s)
            for s in sources
        ],
        return_exceptions=True,
    )


async def periodic_sync_loop(
    repos_dir: Path,
    ssh_keys_dir: Path,
    gitea_servers_dir: Path,
    meta_dir: Path,
) -> None:
    """Poll each source on its own interval.  Run as a background task."""
    # Track next-sync time per source id (in monotonic seconds).
    # Seed every known source with "now + interval" so the first tick after
    # process start does NOT fire an immediate fetch — startup_sync already
    # handled that. Without this, the first tick (at t≈60s) re-fetched every
    # source unconditionally because next_sync.get(sid, 0) returned 0.
    next_sync: dict[str, float] = {}
    initial_sources = await load_sources(meta_dir)
    initial_now = asyncio.get_event_loop().time()
    for entry in initial_sources:
        sid = entry["id"]
        interval_secs = entry.get("sync_interval_minutes", 15) * 60
        next_sync[sid] = initial_now + interval_secs

    # Keep task references alive so they're not garbage-collected mid-run
    _running: set[asyncio.Task[None]] = set()

    while True:
        await asyncio.sleep(60)  # check every minute
        sources = await load_sources(meta_dir)
        now = asyncio.get_event_loop().time()

        for entry in sources:
            sid = entry["id"]
            interval_secs = entry.get("sync_interval_minutes", 15) * 60
            if now >= next_sync.get(sid, 0):
                # Bounded via the shared semaphore so multiple sources don't
                # fetch in parallel on low-core hosts.
                task = asyncio.create_task(
                    _bounded_sync_one(repos_dir, ssh_keys_dir, gitea_servers_dir, meta_dir, entry)
                )
                _running.add(task)
                task.add_done_callback(_running.discard)
                next_sync[sid] = now + interval_secs
