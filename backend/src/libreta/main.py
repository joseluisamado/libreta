import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from libreta import __version__
from libreta.api import assets, pages, search, sources as sources_api, system, watch
from libreta.deps import get_settings
from libreta.errors import LibretaError
from libreta.services.sync import periodic_sync_loop, push_worker, startup_sync
from libreta.storage.search import incremental_reindex

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # Search index warm-up (still uses content_dir for watched/meta storage)
    try:
        n = await incremental_reindex(settings.content_dir, settings.repos_dir)
        if n:
            logger.info("search index: updated %d page(s) on startup", n)
    except Exception:
        logger.warning("search index: startup reindex failed", exc_info=True)

    # Git sources: clone missing, fast-forward existing
    try:
        await startup_sync(settings.repos_dir, settings.ssh_keys_dir, settings.content_dir)
    except Exception:
        logger.warning("sources: startup sync failed", exc_info=True)

    # Launch background tasks
    push_task = asyncio.create_task(
        push_worker(settings.repos_dir, settings.ssh_keys_dir, settings.content_dir)
    )
    sync_task = asyncio.create_task(
        periodic_sync_loop(settings.repos_dir, settings.ssh_keys_dir, settings.content_dir)
    )

    yield

    push_task.cancel()
    sync_task.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(push_task, sync_task, return_exceptions=True)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Libreta",
        version=__version__,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )

    # Dev-only CORS so the Vite dev server (host port 8091) can call the api (host port 8092).
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
    app.include_router(watch.router, prefix="/api/v1", tags=["watch"])
    app.include_router(sources_api.router, prefix="/api/v1", tags=["sources"])

    return app


app = create_app()
