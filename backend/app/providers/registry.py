"""Which provider the analysis jobs use. Tests replace `factory`."""

import os
from collections.abc import Callable

from app.config import settings
from app.providers.base import AnalysisProvider


def _default() -> AnalysisProvider:
    if os.environ.get("CFS_FAKE_PROVIDER") == "e2e":  # browser tests only — never calls a real API
        from app.providers.fake import FakeProvider, e2e_responder

        return FakeProvider(e2e_responder)
    from app.providers.gemini import GeminiProvider

    return GeminiProvider(settings.gemini_api_key)


factory: Callable[[], AnalysisProvider] = _default


def get_provider() -> AnalysisProvider:
    return factory()
