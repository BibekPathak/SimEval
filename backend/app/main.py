"""FastAPI application entry point.

Startup:
  1. create database tables (idempotent; Alembic is the migration path),
  2. sync the simulation registries (tasks/policies) into the DB,
  3. start the bounded local worker and recover any interrupted experiments.

Shutdown stops the worker.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api import routes_experiments, routes_registry
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.db.session import Base, get_engine, session_scope
from backend.app.models import entities  # noqa: F401 - register models on Base.metadata
from backend.app.services.registry_sync import sync_registries
from backend.app.workers.experiment_worker import get_worker
from simulation import __version__

log = get_logger("simeval.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging("DEBUG" if get_settings().debug else "INFO")
    Base.metadata.create_all(bind=get_engine())
    with session_scope() as session:
        sync_registries(session)
    worker = get_worker()
    worker.recover_interrupted()
    worker.start()
    log.info("api started version=%s", __version__)
    try:
        yield
    finally:
        worker.stop()
        log.info("api stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Simulation-driven robot learning evaluation platform",
        lifespan=lifespan,
    )

    # CORS: the Vite dev server proxies /api to this service in development, but
    # direct browser access (e.g. VITE_API_BASE pointing at :8000) is also
    # supported. Origins are configurable; defaults cover local development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic v2 may embed non-serializable objects (e.g. ValueError) in ctx.
        errors = []
        for err in exc.errors():
            clean = {k: v for k, v in err.items() if k != "ctx"}
            ctx = err.get("ctx")
            if isinstance(ctx, dict):
                clean["ctx"] = {
                    k: (str(v) if isinstance(v, BaseException) else v) for k, v in ctx.items()
                }
            errors.append(clean)
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": errors, "status_code": 422},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error path=%s error=%s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "internal server error",
                "status_code": 500,
            },
        )

    app.include_router(routes_registry.router, prefix=settings.api_v1_prefix)
    app.include_router(routes_experiments.router, prefix=settings.api_v1_prefix)

    _mount_dashboard(app)
    return app


def _mount_dashboard(app: FastAPI) -> None:
    """Serve the built dashboard if present (production single-container mode).

    In development the Vite dev server serves the UI and proxies /api here, so
    ``frontend/dist`` does not exist and this is a no-op. When the UI has been
    built (e.g. in the Docker image), serve it from the same origin with an SPA
    fallback, while leaving ``/api`` and ``/docs`` to FastAPI.
    """
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if not dist.is_dir():
        return

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    index_file = dist / "index.html"

    @app.get("/", include_in_schema=False)
    async def _index() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> FileResponse:
        # Unknown non-API paths fall back to the SPA router. Reserved prefixes
        # are excluded so /api, /docs, /redoc, /openapi.json are never shadowed.
        reserved = ("api/", "docs", "redoc", "openapi.json")
        if full_path.startswith(reserved):
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(index_file)


app = create_app()


__all__ = ["app", "create_app"]
