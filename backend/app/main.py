from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import api_router
from app.config import settings
from app.db import init_db
from app.errors import (
    AppError,
    app_error_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.jobs.runner import job_runner
from app.logging import setup_logging
from app.storage import ensure_data_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_data_dirs()
    settings.load_secrets()
    setup_logging(
        settings.data_dir,
        sensitive_tokens=[settings.gemini_api_key] if settings.gemini_api_key else None,
    )
    init_db()
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

    # CORS configuration
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

    # Error Handlers matching SPEC §9
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore
    app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore

    # Mount API routes
    app.include_router(api_router)

    # Serve built frontend if available
    dist_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path:
            target = dist_dir / full_path
            if target.is_file():
                return FileResponse(target)
        index_file = dist_dir / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
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
