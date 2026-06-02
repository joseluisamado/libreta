from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.models import (
    AssetUploadResponse,
    DiffEntry,
    HistoryEntry,
    PageMove,
    PageNode,
    PageRead,
    PageWrite,
    RecentChange,
)
from libreta.storage.assets import replace_asset, store_asset, store_folder_file
from libreta.storage.pages import (
    delete_page as delete_page_storage,
    move_page as move_page_storage,
    read_page,
    walk_tree,
    write_page,
)
from libreta.storage.paths import normalize_page_path, page_to_file
from libreta.storage.repo import (
    commit_page,
    delete_commit,
    get_file_diff,
    get_file_history,
    get_recent_changes,
    move_commit,
    open_repo,
)
from libreta.storage.search import index_page, remove_page_from_index

# Limit upload size at the API boundary to keep tests deterministic and prevent
# accidentally committing huge blobs. Configurable later if needed.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

router = APIRouter(prefix="/pages")


@router.get("/tree", response_model=list[PageNode])
async def get_tree(settings: Annotated[Settings, Depends(get_settings)]) -> list[PageNode]:
    return await walk_tree(settings.content_dir)


def _pages_root(content_dir: Path) -> Path:
    pages_dir = content_dir / "pages"
    return pages_dir if pages_dir.is_dir() else content_dir


async def _upload_into_folder(
    settings: Settings,
    folder: str,
    file: UploadFile,
) -> AssetUploadResponse:
    """Stream an uploaded file into a content folder as a sibling file.

    No size cap — the file is streamed to disk in chunks. Every successful
    upload is committed (R3). ``folder`` is a page-style path ("" = root).
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail="missing filename")
    base_dir = _pages_root(settings.content_dir)
    result = await store_folder_file(
        base_dir,
        folder,
        file.filename,
        file.read,
        repo_root=settings.content_dir,
    )
    repo = open_repo(settings.content_dir)
    await commit_page(repo, result.rel_path, "upload")
    return AssetUploadResponse(
        filename=result.filename,
        size=result.size,
        sha256=result.sha256,
        kind=result.kind,
        deduped=result.deduped,
    )


# Upload a file straight into the content root. Registered before the
# /{path:path} routes so the literal "/files" suffix wins.
@router.post("/files", response_model=AssetUploadResponse)
async def upload_root_file(
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadResponse:
    return await _upload_into_folder(settings, "", file)


# NOTE: /recent must be registered before /{path:path} routes so that the
# literal "/recent" suffix isn't captured by the greedy path parameter.
@router.get("/recent", response_model=list[RecentChange])
async def get_recent(
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = 20,
) -> list[RecentChange]:
    repo = open_repo(settings.content_dir)
    return await get_recent_changes(repo, limit=limit)


# NOTE: /{path:path}/move must be registered before /{path:path} routes so that
# the literal "/move" suffix takes priority over the greedy path parameter.
@router.post("/{path:path}/move", response_model=PageRead)
async def move_page(
    path: str,
    body: PageMove,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    old_rel, new_rel, is_dir_move = await move_page_storage(
        settings.content_dir, path, body.new_path
    )
    repo = open_repo(settings.content_dir)
    await move_commit(repo, old_rel, new_rel, is_dir_move)
    return await read_page(settings.content_dir, body.new_path)


# NOTE: /{path:path}/history must be registered before /{path:path} so that
# the literal "/history" suffix takes priority over the greedy path parameter.
@router.get("/{path:path}/history", response_model=list[HistoryEntry])
async def get_page_history(
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[HistoryEntry]:
    try:
        file_path = page_to_file(settings.content_dir, normalize_page_path(path))
    except Exception:
        return []
    rel_path = str(file_path.relative_to(settings.content_dir))
    repo = open_repo(settings.content_dir)
    return await get_file_history(repo, rel_path)


# NOTE: /{path:path}/assets must be registered before /{path:path} so that
# the literal "/assets" suffix takes priority over the greedy path parameter.
@router.post("/{path:path}/assets", response_model=AssetUploadResponse)
async def upload_asset(
    path: str,
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadResponse:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="missing filename")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")

    result = await store_asset(settings.content_dir, path, file.filename, data, file.content_type)
    if not result.deduped:
        repo = open_repo(settings.content_dir)
        await commit_page(repo, result.rel_path, "attach")
    return AssetUploadResponse(
        filename=result.filename,
        size=result.size,
        sha256=result.sha256,
        kind=result.kind,
        deduped=result.deduped,
    )


# NOTE: /{path:path}/assets/{filename} (PUT) must come before /{path:path}.
# Used by the diagram editor: a re-saved diagram replaces the bytes of an
# existing sidecar file rather than creating a new one with a uniquified name.
@router.put("/{path:path}/assets/{filename}", response_model=AssetUploadResponse)
async def upsert_asset(
    path: str,
    filename: str,
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadResponse:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    result = await replace_asset(settings.content_dir, path, filename, data, file.content_type)
    if not result.deduped:
        repo = open_repo(settings.content_dir)
        await commit_page(repo, result.rel_path, "update")
    return AssetUploadResponse(
        filename=result.filename,
        size=result.size,
        sha256=result.sha256,
        kind=result.kind,
        deduped=result.deduped,
    )


# NOTE: /{path:path}/files (POST) uploads a sibling file into the folder at
# ``path``. Registered before /{path:path} so the literal "/files" suffix wins.
@router.post("/{path:path}/files", response_model=AssetUploadResponse)
async def upload_folder_file(
    path: str,
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadResponse:
    return await _upload_into_folder(settings, path, file)


# NOTE: /{path:path}/diff must also be registered before /{path:path}.
@router.get("/{path:path}/diff", response_model=DiffEntry)
async def get_page_diff(
    path: str,
    a: str,
    b: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DiffEntry:
    file_path = page_to_file(settings.content_dir, normalize_page_path(path))
    rel_path = str(file_path.relative_to(settings.content_dir))
    repo = open_repo(settings.content_dir)
    return await get_file_diff(repo, rel_path, a, b)


@router.get("/{path:path}", response_model=PageRead)
async def get_page(
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    return await read_page(settings.content_dir, path)


@router.put("/{path:path}", response_model=PageRead)
async def put_page(
    path: str,
    body: PageWrite,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    page, verb = await write_page(settings.content_dir, path, body.body)
    file_path = page_to_file(settings.content_dir, normalize_page_path(path))
    rel_path = str(file_path.relative_to(settings.content_dir))
    repo = open_repo(settings.content_dir)
    await commit_page(repo, rel_path, verb)
    background_tasks.add_task(index_page, settings.content_dir, file_path)
    return page


@router.delete("/{path:path}", status_code=204)
async def delete_page(
    path: str,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    rel_path = await delete_page_storage(settings.content_dir, path)
    repo = open_repo(settings.content_dir)
    await delete_commit(repo, rel_path)
    page_path = rel_path.removeprefix("pages/").removesuffix(".md")
    background_tasks.add_task(remove_page_from_index, settings.content_dir, page_path)
