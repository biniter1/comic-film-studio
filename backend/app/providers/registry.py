"""Which provider the analysis jobs use. Tests replace `factory`."""

from collections.abc import Callable

from app.config import settings
from app.providers.base import AnalysisProvider


def _default() -> AnalysisProvider:
    from app.providers.gemini import GeminiProvider

    return GeminiProvider(settings.gemini_api_key)


factory: Callable[[], AnalysisProvider] = _default


def get_provider() -> AnalysisProvider:
    return factory()
