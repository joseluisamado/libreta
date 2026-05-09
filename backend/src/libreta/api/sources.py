from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.errors import AssetNotFoundError, PageNotFoundError
from libreta.models import (
    AssetUploadResponse,
    DirChildren,
    GitSourceCreate,
    GitSourceResponse,
    GitSourceUpdate,
    PageMove,
    PageNode,
    PageRead,
    PageWrite,
    PendingCommit,
    SshKeyCreate,
    SshKeyResponse,
)
from libreta.services.sync import enqueue_push
from libreta.storage import pagefile, sources as src_store, ssh as ssh_store
from libreta.storage.assets import replace_asset, store_asset
from libreta.storage.repo import _delete_commit_sync, _move_commit_sync, commit_page, open_repo
from libreta.storage.sources import _commit_sync

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

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
        from libreta.storage.sources import fetch_and_ff, push_source, record_sync_result

        try:
            # Push local commits first, then pull remote changes
            await push_source(settings.repos_dir, settings.ssh_keys_dir, entry)
        except Exception:
            pass  # push failures are non-fatal; pull may still work
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


@router.get("/{source_id}/pending", response_model=list[PendingCommit])
async def get_pending(
    source_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[PendingCommit]:
    """List local commits not yet pushed to origin for *source_id*.

    Each entry includes the changed page paths so the UI can show a
    "modified pages" list without needing a second round-trip per commit.
    """
    sources = await src_store.load_sources(settings.content_dir)
    entry = next((s for s in sources if s["id"] == source_id), None)
    if entry is None:
        from libreta.errors import GitSourceNotFoundError

        raise GitSourceNotFoundError(source_id)
    branch = entry.get("branch", "main")
    raw = await src_store.list_pending(settings.repos_dir, source_id, branch)
    return [PendingCommit(**r) for r in raw]


@router.get("/{source_id}/tree", response_model=list[PageNode])
async def get_source_tree(
    source_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
    depth: int = 2,
) -> list[PageNode]:
    return await src_store.walk_source_tree(settings.repos_dir, source_id, max_depth=depth)


@router.get("/{source_id}/children/{path:path}", response_model=DirChildren)
async def get_source_children(
    source_id: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DirChildren:
    children, other = await src_store.walk_source_children(settings.repos_dir, source_id, path)
    return DirChildren(children=children, other_files=other)


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
    repo_root = (settings.repos_dir / source_id).resolve()
    try:
        return FileResponse(pagefile.resolve_asset(repo_root, path))
    except PageNotFoundError:
        raise AssetNotFoundError(path) from None


@router.post("/{source_id}/pages/{path:path}/assets", response_model=AssetUploadResponse)
async def upload_source_asset(
    source_id: str,
    path: str,
    file: UploadFile,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadResponse:
    """Upload an attachment scoped to a page in a git source."""
    if file.filename is None:
        raise HTTPException(status_code=400, detail="missing filename")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")

    # page_to_file handles repos with/without a pages/ subdirectory
    local = (settings.repos_dir / source_id).resolve()
    result = await store_asset(local, path, file.filename, data, file.content_type)
    if not result.deduped:
        repo = open_repo(local)
        await commit_page(repo, result.rel_path, "attach")
        background.add_task(enqueue_push, source_id)
    return AssetUploadResponse(
        filename=result.filename,
        size=result.size,
        sha256=result.sha256,
        kind=result.kind,
        deduped=result.deduped,
    )


@router.put(
    "/{source_id}/pages/{path:path}/assets/{filename}",
    response_model=AssetUploadResponse,
)
async def upsert_source_asset(
    source_id: str,
    path: str,
    filename: str,
    file: UploadFile,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadResponse:
    """Replace the bytes of an existing sidecar asset (used by diagram saves)."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    local = (settings.repos_dir / source_id).resolve()
    result = await replace_asset(local, path, filename, data, file.content_type)
    if not result.deduped:
        repo = open_repo(local)
        await commit_page(repo, result.rel_path, "update")
        background.add_task(enqueue_push, source_id)
    return AssetUploadResponse(
        filename=result.filename,
        size=result.size,
        sha256=result.sha256,
        kind=result.kind,
        deduped=result.deduped,
    )


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


@router.post("/{source_id}/folders/{path:path}", status_code=201)
async def create_source_folder(
    source_id: str,
    path: str,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Create an empty directory (with .gitkeep) in a git source."""
    local = (settings.repos_dir / source_id).resolve()
    dir_path = local / path
    if dir_path.exists():
        raise HTTPException(status_code=409, detail=f"folder already exists: {path}")
    dir_path.mkdir(parents=True)
    gitkeep = dir_path / ".gitkeep"
    gitkeep.write_text("")
    rel = str(gitkeep.relative_to(local))
    repo = open_repo(local)
    await asyncio.to_thread(_commit_sync, repo, [rel], f"create {path}/")
    background.add_task(enqueue_push, source_id)


@router.delete("/{source_id}/pages/{path:path}", status_code=204)
async def delete_source_page(
    source_id: str,
    path: str,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Delete a page (or bare directory) and its sidecar from a git source."""
    local = (settings.repos_dir / source_id).resolve()

    md_file = local / f"{path}.md"
    dir_path = local / path

    if md_file.is_file():
        sidecar = md_file.parent / f".{md_file.name}"
        rel = str(md_file.relative_to(local))
        md_file.unlink()
        if sidecar.is_dir():
            for f in sidecar.rglob("*"):
                if f.is_file():
                    f.unlink()
            sidecar.rmdir()
        repo = open_repo(local)
        await asyncio.to_thread(_delete_commit_sync, repo, rel)
    elif dir_path.is_dir():
        # A bare directory may have a .gitkeep — remove it before checking
        gitkeep = dir_path / ".gitkeep"
        if gitkeep.is_file():
            gitkeep.unlink()
        contents = [p for p in dir_path.iterdir() if not p.name.startswith(".")]
        if contents:
            raise HTTPException(status_code=409, detail=f"folder not empty: {path}")
        rel = str(dir_path.relative_to(local)) + "/"
        # Remove any remaining dot-files, then the directory
        for p in dir_path.iterdir():
            p.unlink()
        dir_path.rmdir()
        repo = open_repo(local)
        await asyncio.to_thread(_delete_commit_sync, repo, rel)
    else:
        raise HTTPException(status_code=404, detail=f"page not found: {path}")
    background.add_task(enqueue_push, source_id)


@router.post("/{source_id}/pages/{path:path}/move", response_model=PageRead)
async def move_source_page(
    source_id: str,
    path: str,
    body: PageMove,
    background: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    """Rename/move a page (or bare directory) and its sidecar in a git source."""
    local = (settings.repos_dir / source_id).resolve()

    old_md = local / f"{path}.md"
    old_dir = local / path
    new_md = local / f"{body.new_path}.md"
    new_dir = local / body.new_path

    if old_md.is_file():
        # Rename a page (and its sidecar)
        if new_md.exists() or new_dir.is_dir():
            raise HTTPException(status_code=409, detail=f"target exists: {body.new_path}")
        new_md.parent.mkdir(parents=True, exist_ok=True)
        old_rel = str(old_md.relative_to(local))
        old_md.rename(new_md)
        new_rel = str(new_md.relative_to(local))
        old_sidecar = old_md.parent / f".{old_md.name}"
        if old_sidecar.is_dir():
            new_sidecar = new_md.parent / f".{new_md.name}"
            old_sidecar.rename(new_sidecar)
        repo = open_repo(local)
        await asyncio.to_thread(_move_commit_sync, repo, old_rel, new_rel)
        background.add_task(enqueue_push, source_id)
        return await src_store.read_source_page(settings.repos_dir, source_id, body.new_path)

    elif old_dir.is_dir():
        # Rename a bare directory.
        if new_dir.exists() or new_md.is_file():
            raise HTTPException(status_code=409, detail=f"target exists: {body.new_path}")
        new_dir.parent.mkdir(parents=True, exist_ok=True)
        # If the dir has a .gitkeep, record paths before the rename
        old_gitkeep = old_dir / ".gitkeep"
        has_gitkeep = old_gitkeep.is_file()
        if has_gitkeep:
            old_gk_rel = str(old_gitkeep.relative_to(local))
        old_dir.rename(new_dir)
        if has_gitkeep:
            new_gk_rel = str((new_dir / ".gitkeep").relative_to(local))
            repo = open_repo(local)
            await asyncio.to_thread(_move_commit_sync, repo, old_gk_rel, new_gk_rel)
        background.add_task(enqueue_push, source_id)
        return await src_store.read_source_page(settings.repos_dir, source_id, body.new_path)

    else:
        raise HTTPException(status_code=404, detail=f"page not found: {path}")
