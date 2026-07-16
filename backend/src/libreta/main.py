import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from libreta import __version__
from libreta.api import search, sources as sources_api, system, watch
from libreta.api.mcp import build_mcp
from libreta.config import Settings
from libreta.deps import get_settings
from libreta.errors import LibretaError
from libreta.services.sync import periodic_sync_loop, push_worker, startup_sync
from libreta.storage.search import incremental_reindex

logger = logging.getLogger(__name__)


async def _startup_reindex(settings: Settings) -> None:
    try:
        n = await incremental_reindex(settings.meta_dir, settings.repos_dir)
        if n:
            logger.info("search index: updated %d page(s) on startup", n)
    except Exception:
        logger.warning("search index: startup reindex failed", exc_info=True)


async def _startup_sources_sync(settings: Settings) -> None:
    try:
        await startup_sync(
            settings.repos_dir,
            settings.ssh_keys_dir,
            settings.gitea_servers_dir,
            settings.meta_dir,
        )
    except Exception:
        logger.warning("sources: startup sync failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # Defer reindex and source sync into background tasks so the HTTP server
    # becomes responsive immediately. On low-spec hosts with hundreds of MB of
    # content, doing this work synchronously in lifespan blocks the API for
    # minutes after process start.
    reindex_task = asyncio.create_task(_startup_reindex(settings))
    startup_sync_task = asyncio.create_task(_startup_sources_sync(settings))

    push_task = asyncio.create_task(
        push_worker(
            settings.repos_dir,
            settings.ssh_keys_dir,
            settings.gitea_servers_dir,
            settings.meta_dir,
        )
    )
    sync_task = asyncio.create_task(
        periodic_sync_loop(
            settings.repos_dir,
            settings.ssh_keys_dir,
            settings.gitea_servers_dir,
            settings.meta_dir,
        )
    )

    # The MCP streamable-HTTP transport runs a session manager that must be
    # started/stopped via its own lifespan; chain it in here so the /mcp mount
    # works. (Without this the session manager task group never starts and
    # every MCP request 500s.) The instance is the one create_app() mounted.
    async with app.state.mcp.session_manager.run():
        yield

    for t in (reindex_task, startup_sync_task, push_task, sync_task):
        t.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(
            reindex_task, startup_sync_task, push_task, sync_task, return_exceptions=True
        )


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
    app.include_router(search.router, prefix="/api/v1", tags=["search"])
    app.include_router(watch.router, prefix="/api/v1", tags=["watch"])
    app.include_router(sources_api.router, prefix="/api/v1", tags=["sources"])

    # Mount the MCP streamable-HTTP transport at /mcp (session manager started in
    # lifespan above). Claude Desktop and other MCP clients connect here. A fresh
    # instance per app, stashed on app.state so lifespan can run its session
    # manager — the manager is single-use, so the module-level singleton would
    # break the second create_app() (e.g. in tests). The settings provider routes
    # through dependency_overrides so MCP tools see the same temp dirs as the
    # REST handlers under test (they call storage directly, not via Depends).
    def _mcp_settings() -> Settings:
        provider: Callable[[], Settings] = app.dependency_overrides.get(get_settings, get_settings)
        return provider()

    app.state.mcp = build_mcp(_mcp_settings)
    app.mount("/mcp", app.state.mcp.streamable_http_app())

    return app


app = create_app()
