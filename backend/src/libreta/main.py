import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from libreta import __version__
from libreta.api import assets, pages, search, system
from libreta.deps import get_settings
from libreta.errors import LibretaError
from libreta.storage.search import incremental_reindex

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        n = await incremental_reindex(settings.content_dir)
        if n:
            logger.info("search index: updated %d page(s) on startup", n)
    except Exception:
        logger.warning("search index: startup reindex failed", exc_info=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Libreta",
        version=__version__,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )

    # Dev-only CORS so the Vite dev server (host port 8091) can call the api (host port 8092).
    # In production the SPA is served from the same origin and this is a no-op.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8091", "http://127.0.0.1:8091"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(LibretaError)
    async def libreta_exc_handler(_: Request, exc: LibretaError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    app.include_router(system.router, prefix="/api/v1", tags=["system"])
    app.include_router(pages.router, prefix="/api/v1", tags=["pages"])
    app.include_router(assets.router, prefix="/api/v1", tags=["assets"])
    app.include_router(search.router, prefix="/api/v1", tags=["search"])

    return app


app = create_app()
