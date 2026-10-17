"""Test-wide setup: every test session uses a throw-away data dir (never the user's)."""

import os
import tempfile

os.environ["CFS_DATA_DIR"] = tempfile.mkdtemp(prefix="cfs-test-")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_waits(monkeypatch):
    """Provider retry backoff and the shared rate limiter must never really sleep in tests.
    Tests that check those mechanisms pass their own sleep_fn / rpm explicitly."""
    from app.config import settings
    from app.providers import retry

    monkeypatch.setitem(retry.call_with_retry.__kwdefaults__, "sleep_fn", lambda s: None)
    monkeypatch.setattr(settings, "analysis_rpm", 0, raising=False)
    retry.rate_limiter.reset()
