from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.errors import WatchedFolderAlreadyExistsError
from libreta.models import (
    PageNode,
    PageRead,
    PageWrite,
    WatchedFolderCreate,
    WatchedFolderResponse,
)
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


@router.get("/{label}/children/{path:path}", response_model=list[PageNode])
async def get_watched_children(
    label: str,
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[PageNode]:
    config = await load_watched_config(settings.content_dir)
    entry = next((e for e in config if e["label"] == label), None)
    if entry is None:
        return []
    watched_root = Path(entry["path"]).expanduser().resolve()
    try:
        _, _ = await resolve_watched_file(settings.content_dir, label, path)
    except Exception:
        return []
    return await walk_watched_children(watched_root, path)


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
        raise HTTPException(status_code=409, detail=f"folder already exists: {path}")


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
