import subprocess
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.errors import AppError
from app.providers.gemini_check import check_gemini_key

router = APIRouter(prefix="/settings", tags=["settings"])


def check_ffmpeg() -> tuple[bool, Optional[str]]:
    try:
        res = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            first_line = res.stdout.splitlines()[0] if res.stdout else "ffmpeg available"
            return True, first_line
    except Exception:
        pass
    return False, None


class SettingsUpdate(BaseModel):
    job_concurrency: Optional[int] = None
    max_parallel_muse_tabs: Optional[int] = None
    muse_clip_seconds: Optional[float] = None
    analysis_model_vision: Optional[str] = None
    analysis_model_text: Optional[str] = None
    # kept for backward compatibility; prefer PUT /settings/gemini-key
    gemini_api_key: Optional[str] = None


class GeminiKeyIn(BaseModel):
    api_key: str


def _key_hint() -> Optional[str]:
    k = settings.gemini_api_key
    return f"…{k[-4:]}" if k and len(k) >= 8 else None


@router.get("")
def get_settings() -> dict[str, Any]:
    has_ffmpeg, ffmpeg_ver = check_ffmpeg()
    return {
        "data_dir": str(settings.data_dir),
        "host": settings.host,
        "port": settings.port,
        "job_concurrency": settings.job_concurrency,
        "max_parallel_muse_tabs": settings.max_parallel_muse_tabs,
        "muse_clip_seconds": settings.muse_clip_seconds,
        "analysis_model_vision": settings.analysis_model_vision,
        "analysis_model_text": settings.analysis_model_text,
        "gemini_configured": bool(settings.gemini_api_key),
        "gemini_key_hint": _key_hint(),
        "ffmpeg_available": has_ffmpeg,
        "ffmpeg_version": ffmpeg_ver,
    }


@router.put("")
def update_settings(update: SettingsUpdate) -> dict[str, Any]:
    if update.job_concurrency is not None:
        settings.job_concurrency = max(1, min(8, update.job_concurrency))
    if update.max_parallel_muse_tabs is not None:
        settings.max_parallel_muse_tabs = max(1, min(16, update.max_parallel_muse_tabs))
    if update.muse_clip_seconds is not None:
        settings.muse_clip_seconds = max(1.0, min(30.0, update.muse_clip_seconds))
    if update.analysis_model_vision:
        settings.analysis_model_vision = update.analysis_model_vision.strip()
    if update.analysis_model_text:
        settings.analysis_model_text = update.analysis_model_text.strip()
    settings.save_overrides()  # survive restarts
    if update.gemini_api_key is not None:
        settings.save_gemini_key(update.gemini_api_key.strip() or None)
    return get_settings()


@router.put("/gemini-key")
def set_gemini_key(body: GeminiKeyIn) -> dict[str, Any]:
    key = body.api_key.strip()
    if len(key) < 20 or any(c.isspace() for c in key):
        raise AppError(
            "VALIDATION_FAILED",
            "API key trông không đúng (quá ngắn hoặc có khoảng trắng). Hãy copy lại từ AI Studio.",
            status_code=422,
        )
    settings.save_gemini_key(key)
    return get_settings()


@router.delete("/gemini-key")
def delete_gemini_key() -> dict[str, Any]:
    settings.save_gemini_key(None)
    return get_settings()


@router.post("/gemini-key/test")
def test_gemini_key() -> dict[str, Any]:
    if not settings.gemini_api_key:
        raise AppError("GEMINI_NOT_CONFIGURED", "Chưa có API key Gemini", status_code=409)
    r = check_gemini_key(settings.gemini_api_key, settings.analysis_model_vision)
    return {"ok": r.ok, "message_vi": r.message_vi, "model": r.model}


@router.get("/providers/status")
def get_providers_status() -> dict[str, Any]:
    has_ffmpeg, ffmpeg_ver = check_ffmpeg()
    return {
        "providers": {
            "gemini": {
                "configured": bool(settings.gemini_api_key),
                "status": "configured" if settings.gemini_api_key else "not_configured",
            }
        },
        "tools": {
            "ffmpeg": {
                "available": has_ffmpeg,
                "version": ffmpeg_ver,
                "warning": None
                if has_ffmpeg
                else "Chưa cài đặt ffmpeg hoặc chưa thêm vào PATH hệ thống.",
            }
        },
    }
