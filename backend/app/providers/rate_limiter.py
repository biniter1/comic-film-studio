"""Shared rate limiter across all analysis providers (Gemini & OpenAICompat)."""

import threading
import time

from app.config import settings


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._timestamps: list[float] = []

    def reset(self) -> None:
        with self._lock:
            self._timestamps.clear()

    def acquire(self, rpm: int | None = None, sleep_fn=time.sleep) -> None:
        limit = rpm if rpm is not None else getattr(settings, "analysis_rpm", 4)
        if limit <= 0:
            return

        min_spacing = 60.0 / limit

        while True:
            with self._lock:
                now = time.monotonic()
                # Remove timestamps older than 60s
                self._timestamps = [t for t in self._timestamps if now - t < 60.0]

                wait_time = 0.0
                if len(self._timestamps) >= limit:
                    wait_time = max(wait_time, 60.0 - (now - self._timestamps[0]))
                if self._timestamps:
                    time_since_last = now - self._timestamps[-1]
                    if time_since_last < min_spacing:
                        wait_time = max(wait_time, min_spacing - time_since_last)

                if wait_time <= 0.001:
                    self._timestamps.append(time.monotonic())
                    return

            sleep_fn(min(wait_time, 1.0))


rate_limiter = RateLimiter()
