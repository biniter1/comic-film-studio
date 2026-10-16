from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.1.0",
    }
