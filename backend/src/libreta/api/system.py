from typing import Annotated

from fastapi import APIRouter, Depends

from libreta import __version__
from libreta.config import Settings
from libreta.deps import get_settings
from libreta.models import HealthResponse, InfoResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse)
async def readyz(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    ready = settings.content_dir.exists()
    return HealthResponse(status="ready" if ready else "not-ready")


@router.get("/info", response_model=InfoResponse)
async def info(settings: Annotated[Settings, Depends(get_settings)]) -> InfoResponse:
    return InfoResponse(
        name="libreta",
        version=__version__,
        content_dir=str(settings.content_dir),
        content_dir_exists=settings.content_dir.exists(),
    )
