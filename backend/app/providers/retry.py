"""Provider retry and rate-limiting wrapper (SPEC §2, §4)."""

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

from app.jobs.registry import current_job_ctx
from app.providers.base import ProviderError
from app.providers.rate_limiter import RateLimiter, rate_limiter

logger = logging.getLogger(__name__)
T = TypeVar("T")


def call_with_retry(
    fn: Callable[[], T],
    *,
    provider_name: str,
    max_retries: int = 6,
    base_delay: float = 5.0,
    max_delay: float = 60.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    limiter: RateLimiter | None = rate_limiter,
) -> T:
    """Execute provider call with rate-limiting and exponential backoff retry for transient errors.

    Retries up to `max_retries` (default 6) for errors with category 'transient' (503, 500,
    502, 504, 429-rate, timeout). Errors with category 'quota', 'permanent', or
    'invalid_output' are never retried.
    """
    for attempt in range(max_retries + 1):
        if limiter is not None:
            limiter.acquire()
        try:
            return fn()
        except ProviderError as e:
            if e.category != "transient" or attempt >= max_retries:
                raise
            delay = min(max_delay, base_delay * (2**attempt)) + random.uniform(0.5, 2.0)
            msg = (
                f"{provider_name}: lỗi tạm thời ({e.message_vi}), "
                f"thử lại lần {attempt + 1}/{max_retries} sau {delay:.1f}s..."
            )
            ctx = current_job_ctx.get()
            if ctx:
                ctx.log(msg)
            logger.warning(msg)
            sleep_fn(delay)
    raise RuntimeError("Unreachable")
