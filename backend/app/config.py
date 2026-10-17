import json
import logging
import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CFS_",
        extra="ignore",
    )

    data_dir: Path = (
        Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "ComicFilmStudio"
    )
    host: str = "127.0.0.1"
    port: int = 8765
    job_concurrency: int = 2
    max_parallel_muse_tabs: int = 4
    muse_clip_seconds: float = 4.0
    gemini_api_key: Optional[str] = None
    # Phase 2a: model ids live here only (never hard-coded elsewhere)
    analysis_model_vision: str = "gemini-flash-latest"
    analysis_model_text: str = "gemini-pro-latest"
    analysis_rpm: int = 4
    read_batch_size: int = 6
    # OpenAI Compat provider settings
    analysis_provider: str = "gemini"  # "gemini" | "openai_compat"
    openai_base_url: str = "https://revidapi.com/v1"
    openai_auth_header: str = "x-api-key"  # "x-api-key" | "authorization-bearer"
    openai_reasoning_effort: str = "low"  # "low" | "medium" | "high"
    openai_compat_api_key: Optional[str] = None

    def load_secrets(self) -> None:
        """Read secrets.env from data_dir if present."""
        secrets_file = self.data_dir / "secrets.env"
        if secrets_file.exists():
            try:
                content = secrets_file.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key == "GEMINI_API_KEY" and not self.gemini_api_key:
                        self.gemini_api_key = val
                    elif key == "CFS_GEMINI_API_KEY" and not self.gemini_api_key:
                        self.gemini_api_key = val
                    elif key == "OPENAI_COMPAT_API_KEY" and not self.openai_compat_api_key:
                        self.openai_compat_api_key = val
                    elif key == "CFS_OPENAI_COMPAT_API_KEY" and not self.openai_compat_api_key:
                        self.openai_compat_api_key = val
            except Exception:
                pass

    # ------------------------------------------------------------------
    # User-editable parameters persisted in data_dir/settings.json
    # (secrets stay in secrets.env; never in settings.json)
    # ------------------------------------------------------------------
    PERSISTED: tuple[str, ...] = (
        "job_concurrency",
        "max_parallel_muse_tabs",
        "muse_clip_seconds",
        "analysis_model_vision",
        "analysis_model_text",
        "analysis_provider",
        "openai_base_url",
        "openai_auth_header",
        "openai_reasoning_effort",
        "analysis_rpm",
        "read_batch_size",
    )

    def load_overrides(self) -> None:
        f = self.data_dir / "settings.json"
        if not f.exists():
            return
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logging.getLogger(__name__).warning("settings.json is unreadable; using defaults")
            return
        for k in self.PERSISTED:
            if k in data:
                setattr(self, k, data[k])

    def save_overrides(self) -> None:
        f = self.data_dir / "settings.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({k: getattr(self, k) for k in self.PERSISTED}, indent=2), encoding="utf-8"
        )
        tmp.replace(f)

    def _write_secrets(self) -> None:
        f = self.data_dir / "secrets.env"
        f.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if self.gemini_api_key:
            lines.append(f"GEMINI_API_KEY={self.gemini_api_key}")
        if self.openai_compat_api_key:
            lines.append(f"OPENAI_COMPAT_API_KEY={self.openai_compat_api_key}")
        f.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def save_gemini_key(self, key: Optional[str]) -> None:
        self.gemini_api_key = key or None
        self._write_secrets()

    def save_openai_key(self, key: Optional[str]) -> None:
        self.openai_compat_api_key = key or None
        self._write_secrets()


settings = Settings()
