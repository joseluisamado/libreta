from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.errors import (
    PageNotFoundError,
    WatchedFolderAlreadyExistsError,
    WatchedLabelNotFoundError,
)
from libreta.models import (
    AssetUploadResponse,
    DirChildren,
    PageNode,
    PageRead,
    PageWrite,
    WatchedFolderCreate,
    WatchedFolderResponse,
    WatchedFolderUpdate,
)
from libreta.storage import pagefile
from libreta.storage.assets import store_folder_file
from libreta.storage.watched import (
    create_watched_folder,
    delete_watched_page,
    load_watched_config,
    read_watched_page,
    resolve_watched_file,
    save_watched_config,
    walk_watched_children,
    walk_watched_tree,
    write_watched_page,
)

router = APIRouter(prefix="/watch")


@router.get("/folders", response_model=list[WatchedFolderResponse])
async def list_watched_folders(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[WatchedFolderResponse]:
    config = await load_watched_config(settings.content_dir)
    return [
        WatchedFolderResponse(
            label=e["label"],
            path=e["path"],
            exists=Path(e["path"]).expanduser().resolve().exists(),
        )
        for e in config
    ]


@router.post("/folders", response_model=WatchedFolderResponse, status_code=201)
async def add_watched_folder(
    body: WatchedFolderCreate,
    settings: Annotated[Settings, Depends(get_settings)],
) -> WatchedFolderResponse:
    config = await load_watched_config(settings.content_dir)
    if any(e["label"] == body.label for e in config):
        raise WatchedFolderAlreadyExistsError(body.label)

    folder_path = Path(body.path).expanduser().resolve()
    # Accept even if not currently accessible — the user may mount it later.
    exists = folder_path.exists()
    config.append({"label": body.label, "path": str(folder_path)})
    await save_watched_config(settings.content_dir, config)
    return WatchedFolderResponse(label=body.label, path=str(folder_path), exists=exists)


@router.put("/folders/{label}", response_model=WatchedFolderResponse)
async def update_watched_folder(
    label: str,
    body: WatchedFolderUpdate,
    settings: Annotated[Settings, Depends(get_settings)],
) -> WatchedFolderResponse:
    """Edit a watched folder's label and/or path.

    The label is the config key, so a rename re-keys the entry. Renaming to a
    label already used by another folder is rejected.
    """
    config = await load_watched_config(settings.content_dir)
    idx = next((i for i, e in enumerate(config) if e["label"] == label), None)
    if idx is None:
        raise WatchedLabelNotFoundError(label)
    if body.label != label and any(e["label"] == body.label for e in config):
        raise WatchedFolderAlreadyExistsError(body.label)

    folder_path = Path(body.path).expanduser().resolve()
    config[idx] = {"label": body.label, "path": str(folder_path)}
    await save_watched_config(settings.content_dir, config)
    return WatchedFolderResponse(
        label=body.label, path=str(folder_path), exists=folder_path.exists()
    )


@router.delete("/folders/{label}", status_code=204)
async def remove_watched_folder(
    label: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    config = await load_watched_config(settings.content_dir)
    config = [e for e in config if e["label"] != label]
    await save_watched_config(settings.content_dir, config)


@router.get("/{label}/tree", response_model=list[PageNode])
async def get_watched_tree(
    label: str,
    settings: Annotated[Settings, Depends(get_settings)],
    depth: int = 2,
) -> list[PageNode]:
    config = await load_watched_config(settings.content_dir)
    entry = next((e for e in config if e["label"] == label), None)
    if entry is None:
        return []
    watched_root = Path(entry["path"]).expanduser().resolve()
    return await walk_watched_tree(watched_root, max_depth=depth)


@router.get("/{label}/children/{path:path}", response_model=DirChildren)
async def get_watched_children(
    label: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DirChildren:
    config = await load_watched_config(settings.content_dir)
    entry = next((e for e in config if e["label"] == label), None)
    if entry is None:
        return DirChildren()
    watched_root = Path(entry["path"]).expanduser().resolve()
    try:
        _, _ = await resolve_watched_file(settings.content_dir, label, path)
    except Exception:
        return DirChildren()
    children, other = await walk_watched_children(watched_root, path)
    return DirChildren(children=children, other_files=other)


@router.get("/{label}/assets/{path:path}")
async def get_watched_asset(
    label: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    watched_root, _ = await resolve_watched_file(settings.content_dir, label, path)
    try:
        return FileResponse(pagefile.resolve_asset(watched_root, path))
    except PageNotFoundError:
        raise HTTPException(status_code=404, detail=f"asset not found: {path}") from None


@router.get("/{label}/{path:path}", response_model=PageRead)
async def get_watched_page(
    label: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    watched_root, _ = await resolve_watched_file(settings.content_dir, label, path)
    return await read_watched_page(watched_root, path or "")


@router.put("/{label}/{path:path}", response_model=PageRead)
async def put_watched_page(
    label: str,
    path: str,
    body: PageWrite,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PageRead:
    watched_root, _ = await resolve_watched_file(settings.content_dir, label, path)
    page, _ = await write_watched_page(watched_root, path, body.body)
    return page


async def _watched_root(settings: Settings, label: str) -> Path:
    config = await load_watched_config(settings.content_dir)
    entry = next((e for e in config if e["label"] == label), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"watched folder {label!r} not found")
    return Path(entry["path"]).expanduser().resolve()


async def _upload_into_watched_folder(
    settings: Settings,
    label: str,
    folder: str,
    file: UploadFile,
) -> AssetUploadResponse:
    """Stream an uploaded file into a watched folder as a sibling file.

    Watched folders are plain on-disk directories (no git), so there is no
    commit — the file is simply streamed to disk. No size cap.
    """
    if file.filename is None:
        raise HTTPException(status_code=400, detail="missing filename")
    watched_root = await _watched_root(settings, label)
    result = await store_folder_file(watched_root, folder, file.filename, file.read)
    return AssetUploadResponse(
        filename=result.filename,
        size=result.size,
        sha256=result.sha256,
        kind=result.kind,
        deduped=result.deduped,
    )


@router.post("/{label}/files", response_model=AssetUploadResponse)
async def upload_watched_root_file(
    label: str,
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadResponse:
    return await _upload_into_watched_folder(settings, label, "", file)


# NOTE: registered before /{label}/{path:path}; the "/folders/.../files" suffix
# disambiguates from the page routes.
@router.post("/{label}/folders/{path:path}/files", response_model=AssetUploadResponse)
async def upload_watched_folder_file(
    label: str,
    path: str,
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssetUploadResponse:
    return await _upload_into_watched_folder(settings, label, path, file)


@router.post("/{label}/folders/{path:path}", status_code=201)
async def create_watched_folder_endpoint(
    label: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    config = await load_watched_config(settings.content_dir)
    entry = next((e for e in config if e["label"] == label), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"watched folder {label!r} not found")
    watched_root = Path(entry["path"]).expanduser().resolve()
    try:
        await create_watched_folder(watched_root, path)
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"folder already exists: {path}") from None


@router.delete("/{label}/{path:path}", status_code=204)
async def delete_watched_page_endpoint(
    label: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    config = await load_watched_config(settings.content_dir)
    entry = next((e for e in config if e["label"] == label), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"watched folder {label!r} not found")
    watched_root = Path(entry["path"]).expanduser().resolve()
    await delete_watched_page(watched_root, path)
