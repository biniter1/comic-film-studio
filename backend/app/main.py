import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.config import settings
from app.errors import (
    AppError,
    app_error_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.jobs.event_bus import event_bus
from app.jobs.runner import job_runner
from app.logging import setup_logging
from app.storage import ensure_data_dirs

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _run_migrations() -> None:
    """B6: Run `alembic upgrade head` on startup using absolute path to alembic.ini."""
    alembic_ini = _BACKEND_DIR / "alembic.ini"
    cfg = AlembicConfig(str(alembic_ini))
    # Override sqlalchemy.url so it uses the configured data_dir
    db_path = settings.data_dir / "cfs.db"
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    alembic_command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_data_dirs()
    settings.load_secrets()
    setup_logging(
        settings.data_dir,
        sensitive_tokens=[settings.gemini_api_key] if settings.gemini_api_key else None,
    )

    # B6: apply all pending Alembic migrations before opening the app
    try:
        _run_migrations()
    except Exception:
        logger.exception("Failed to run Alembic migrations — proceeding with existing schema")

    # B1: bind the main event loop so publish_threadsafe works from sync endpoints
    event_bus.bind_loop(asyncio.get_running_loop())

    await job_runner.start()
    yield
    # Shutdown
    await job_runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Comic Film Studio",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:8765",
            "http://localhost:8765",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers (SPEC §9)
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore[arg-type]

    # Mount API routes FIRST so /api/* never falls through to the SPA handler
    app.include_router(api_router)

    # Serve built frontend safely (B5)
    dist_dir = _BACKEND_DIR.parent / "frontend" / "dist"

    if dist_dir.is_dir():
        # Serve /assets via StaticFiles — no path traversal possible
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            # B5: only serve files that are inside dist_dir
            if full_path:
                try:
                    # Decode percent-encoded characters before checking
                    from urllib.parse import unquote

                    decoded = unquote(full_path)
                    candidate = (dist_dir / decoded).resolve()
                    # Must be inside dist_dir and must exist as a file
                    candidate.relative_to(dist_dir.resolve())
                    if candidate.is_file():
                        return FileResponse(candidate)
                except (ValueError, Exception):
                    pass  # path traversal or decode error → fall through to index.html
            return FileResponse(dist_dir / "index.html")

    else:

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_no_frontend(full_path: str) -> dict:  # type: ignore[misc]
            return {
                "name": "Comic Film Studio",
                "status": "online",
                "message": "Frontend chưa được build. Vui lòng chạy 'npm run build' trong frontend/",
            }

    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
