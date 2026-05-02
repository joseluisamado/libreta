from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from libreta.config import Settings
from libreta.deps import get_settings
from libreta.storage.assets import resolve_asset

router = APIRouter(prefix="/assets")


@router.get("/{path:path}")
async def get_asset(
    path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    file = resolve_asset(settings.content_dir, path)
    return FileResponse(file)
