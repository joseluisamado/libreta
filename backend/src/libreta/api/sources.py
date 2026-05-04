from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.errors import AssetNotFoundError, InvalidPathError
from libreta.models import (
    GitSourceCreate,
    GitSourceResponse,
    GitSourceUpdate,
    PageNode,
    PageRead,
    PageWrite,
    SshKeyCreate,
    SshKeyResponse,
)
from libreta.services.sync import enqueue_push
from libreta.storage import sources as src_store, ssh as ssh_store

router = APIRouter(prefix="/sources")


# ---------------------------------------------------------------------------
# SSH key management
# ---------------------------------------------------------------------------


@router.get("/keys", response_model=list[SshKeyResponse])
async def list_ssh_keys(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[SshKeyResponse]:
    return await ssh_store.list_keys(settings.ssh_keys_dir)


@router.post("/keys", response_model=SshKeyResponse, status_code=201)
async def add_ssh_key(
    body: SshKeyCreate,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SshKeyResponse:
    return await ssh_store.add_key(settings.ssh_keys_dir, body.label, body.private_key)


@router.delete("/keys/{key_id}", status_code=204)
async def delete_ssh_key(
    key_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    await ssh_store.remove_key(settings.ssh_keys_dir, key_id)


# ---------------------------------------------------------------------------
# Source CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[GitSourceResponse])
async def list_sources(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[GitSourceResponse]:
    return await src_store.list_sources(settings.content_dir, settings.repos_dir)


@router.post("", response_model=GitSourceResponse, status_code=201)
async def add_source(
    body: GitSourceCreate,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitSourceResponse:
    result = await src_store.add_source(settings.content_dir, settings.repos_dir, body)
    # Clone in the background so the HTTP response returns immediately
    sources = await src_store.load_sources(settings.content_dir)
    entry = next((s for s in sources if s["id"] == body.id), None)
    if entry:
        background.add_task(
            _clone_and_record,
            settings.repos_dir,
            settings.ssh_keys_dir,
            settings.content_dir,
            entry,
        )
    return result


async def _clone_and_record(
    repos_dir: Path,
    ssh_keys_dir: Path,
    content_dir: Path,
    entry: dict,  # type: ignore[type-arg]
) -> None:
    try:
        await src_store.clone_source(repos_dir, ssh_keys_dir, entry)
        await src_store.record_sync_result(content_dir, entry["id"], None)
    except Exception as exc:
        await src_store.record_sync_result(content_dir, entry["id"], str(exc))


@router.put("/{source_id}", response_model=GitSourceResponse)
async def update_source(
    source_id: str,
    body: GitSourceUpdate,
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitSourceResponse:
    return await src_store.update_source(settings.content_dir, settings.repos_dir, source_id, body)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    await src_store.remove_source(settings.content_dir, source_id)


@router.post("/{source_id}/sync", response_model=GitSourceResponse)
async def trigger_sync(
    source_id: str,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitSourceResponse:
    sources = await src_store.load_sources(settings.content_dir)
    entry = next((s for s in sources if s["id"] == source_id), None)
    if entry is None:
        from libreta.errors import GitSourceNotFoundError

        raise GitSourceNotFoundError(source_id)

    async def _sync() -> None:
        from libreta.storage.sources import fetch_and_ff, record_sync_result

        try:
            await fetch_and_ff(settings.repos_dir, settings.ssh_keys_dir, entry)
            await record_sync_result(settings.content_dir, source_id, None)
        except Exception as exc:
            await record_sync_result(settings.content_dir, source_id, str(exc))

    background.add_task(_sync)
    # Return current state (sync runs in background)
    return await src_store.update_source(
        settings.content_dir,
        settings.repos_dir,
        source_id,
        GitSourceUpdate(),
    )


# ---------------------------------------------------------------------------
# Page tree + read/write for a source
# ---------------------------------------------------------------------------


@router.get("/{source_id}/tree", response_model=list[PageNode])
async def get_source_tree(
    source_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[PageNode]:
    return await src_store.walk_source_tree(settings.repos_dir, source_id)


@router.get("/{source_id}/pages/{path:path}", response_model=PageRead)
async def get_source_page(
    source_id: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    return await src_store.read_source_page(settings.repos_dir, source_id, path)


@router.get("/{source_id}/assets/{path:path}")
async def get_source_asset(
    source_id: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    if not path or path.startswith("/"):
        raise InvalidPathError(f"asset path must be relative and non-empty: {path!r}")
    parts = path.split("/")
    for p in parts:
        if not p or p in {".", ".."} or p.startswith("."):
            raise InvalidPathError(f"invalid asset segment {p!r} in {path!r}")
        if "\x00" in p:
            raise InvalidPathError("null byte in path")
    if path.endswith(".md"):
        raise InvalidPathError("markdown pages are not served via /assets")
    repo_root = (settings.repos_dir / source_id).resolve()
    candidate = (repo_root / Path(*parts)).resolve()
    if repo_root not in candidate.parents and candidate != repo_root:
        raise InvalidPathError("asset path escapes repository directory")
    if not candidate.is_file():
        raise AssetNotFoundError(path)
    return FileResponse(candidate)


@router.put("/{source_id}/pages/{path:path}", response_model=PageRead)
async def put_source_page(
    source_id: str,
    path: str,
    body: PageWrite,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    result = await src_store.write_source_page(
        settings.repos_dir,
        settings.ssh_keys_dir,
        settings.content_dir,
        source_id,
        path,
        body.body,
    )
    background.add_task(enqueue_push, source_id)
    return result
