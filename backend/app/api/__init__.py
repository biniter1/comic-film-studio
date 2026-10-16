from fastapi import APIRouter

from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.settings import router as settings_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(jobs_router)
api_router.include_router(events_router)
api_router.include_router(settings_router)

__all__ = ["api_router"]
