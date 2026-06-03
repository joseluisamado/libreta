from typing import Annotated

from fastapi import APIRouter, Depends

from libreta import __version__
from libreta.config import Settings
from libreta.deps import get_settings
from libreta.models import ClientConfig, HealthResponse, InfoResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse)
async def readyz(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    ready = settings.meta_dir.exists()
    return HealthResponse(status="ready" if ready else "not-ready")


@router.get("/config", response_model=ClientConfig)
async def client_config(settings: Annotated[Settings, Depends(get_settings)]) -> ClientConfig:
    return ClientConfig(drawio_url=settings.drawio_url)


@router.get("/info", response_model=InfoResponse)
async def info(settings: Annotated[Settings, Depends(get_settings)]) -> InfoResponse:
    return InfoResponse(
        name="libreta",
        version=__version__,
        meta_dir=str(settings.meta_dir),
        meta_dir_exists=settings.meta_dir.exists(),
    )
