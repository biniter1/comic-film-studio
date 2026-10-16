import contextvars
import inspect
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class JobError(Exception):
    def __init__(
        self,
        category: str,  # transient | invalid_output | permanent | quota
        message: str,
        user_action_required: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.user_action_required = user_action_required


class JobContext:
    """Passed to every job handler — safe to call from sync or async code."""

    def __init__(
        self,
        job_id: str,
        payload: dict[str, Any],
        log_file: Path,
        progress_callback: Callable[[float, Optional[str]], None],
        cancel_check: Callable[[], bool],
    ) -> None:
        self.job_id = job_id
        self.payload = payload
        self.log_file = log_file
        self._progress_callback = progress_callback
        self._cancel_check = cancel_check

    def report_progress(self, progress: float, message: Optional[str] = None) -> None:
        clamped = max(0.0, min(1.0, float(progress)))
        self._progress_callback(clamped, message)
        if message:
            self.log(f"[PROGRESS {int(clamped * 100)}%] {message}")

    def log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        line = f"[{ts}] {message}\n"
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def is_cancelled(self) -> bool:
        return self._cancel_check()


current_job_ctx: contextvars.ContextVar[Optional[JobContext]] = contextvars.ContextVar(
    "current_job_ctx", default=None
)


# Handler may be either `async def` (non-blocking) or `def` (CPU/IO-heavy).
# Runner detects via inspect.iscoroutinefunction and dispatches accordingly.
SyncHandlerFunc = Callable[[JobContext], None]
AsyncHandlerFunc = Callable[[JobContext], Awaitable[None]]
JobHandlerFunc = SyncHandlerFunc | AsyncHandlerFunc

_JOB_HANDLERS: dict[str, JobHandlerFunc] = {}

_SECRET_TOKENS = {"key", "apikey", "token", "secret", "password", "passwd", "credential"}


def _check_payload(payload: dict[str, Any]) -> None:
    """Raise ValueError if payload contains secret-like keys (per SPEC §5.6).

    Matching is per snake/kebab-case token so that e.g. ``keyframe_asset_id`` is allowed
    while ``api_key`` / ``access-token`` are rejected.
    """
    for k in payload:
        tokens = {t for t in re.split(r"[_\-\s.]+", k.lower()) if t}
        if tokens & _SECRET_TOKENS:
            raise ValueError(
                f"Payload key '{k}' looks like a secret. "
                "Job payloads must contain only IDs and technical parameters."
            )


def job_handler(job_type: str) -> Callable[[JobHandlerFunc], JobHandlerFunc]:
    def decorator(fn: JobHandlerFunc) -> JobHandlerFunc:
        _JOB_HANDLERS[job_type] = fn
        return fn

    return decorator


def get_handler(job_type: str) -> Optional[JobHandlerFunc]:
    return _JOB_HANDLERS.get(job_type)


def is_async_handler(fn: JobHandlerFunc) -> bool:
    return inspect.iscoroutinefunction(fn)
