import subprocess
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

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
    gemini_api_key: Optional[str] = None


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
        "gemini_configured": bool(settings.gemini_api_key),
        "ffmpeg_available": has_ffmpeg,
        "ffmpeg_version": ffmpeg_ver,
    }


@router.put("")
def update_settings(update: SettingsUpdate) -> dict[str, Any]:
    if update.job_concurrency is not None:
        settings.job_concurrency = max(1, update.job_concurrency)
    if update.max_parallel_muse_tabs is not None:
        settings.max_parallel_muse_tabs = max(1, update.max_parallel_muse_tabs)
    if update.muse_clip_seconds is not None:
        settings.muse_clip_seconds = max(1.0, update.muse_clip_seconds)

    if update.gemini_api_key is not None:
        key_val = update.gemini_api_key.strip()
        settings.gemini_api_key = key_val if key_val else None
        # Save to secrets.env in data_dir (never in repo)
        secrets_file = settings.data_dir / "secrets.env"
        secrets_file.parent.mkdir(parents=True, exist_ok=True)
        secrets_file.write_text(
            f"GEMINI_API_KEY={settings.gemini_api_key or ''}\n", encoding="utf-8"
        )

    return get_settings()


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
