from types import SimpleNamespace

import pytest
from google.genai import errors

from app.providers.base import ImagePart, ProviderError, ProviderRequest
from app.providers.gemini import GeminiProvider, classify_client_error


def _err(code, message, status="X"):
    return errors.ClientError(code, {"error": {"code": code, "message": message, "status": status}})


def test_rate_limit_is_transient():
    e = classify_client_error(
        429, str(_err(429, "Rate limit: requests per minute", "RESOURCE_EXHAUSTED"))
    )
    assert e.category == "transient"


def test_daily_quota_is_quota_with_user_action():
    e = classify_client_error(
        429, str(_err(429, "Quota exceeded ... limit: 50 per day", "RESOURCE_EXHAUSTED"))
    )
    assert e.category == "quota" and "thủ công" in (e.user_action_required or "")


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_client_errors_are_permanent(code):
    assert classify_client_error(code, "bad").category == "permanent"


def test_missing_key_is_permanent():
    with pytest.raises(ProviderError) as e:
        GeminiProvider(None)
    assert e.value.category == "permanent" and "Cài đặt" in (e.value.user_action_required or "")


def test_generate_maps_sdk_errors(monkeypatch):
    p = GeminiProvider("x" * 39)

    def boom(**kw):
        raise _err(429, "limit 50 per day", "RESOURCE_EXHAUSTED")

    p.client = SimpleNamespace(models=SimpleNamespace(generate_content=boom))
    with pytest.raises(ProviderError) as e:
        p.generate(ProviderRequest("read", "m", "s", "u"))
    assert e.value.category == "quota"

    def server(**kw):
        raise errors.ServerError(503, {"error": {"code": 503, "message": "overloaded"}})

    p.client = SimpleNamespace(models=SimpleNamespace(generate_content=server))
    with pytest.raises(ProviderError) as e:
        p.generate(ProviderRequest("read", "m", "s", "u"))
    assert e.value.category == "transient"


def test_generate_returns_text(monkeypatch, tmp_path):
    from PIL import Image

    img = tmp_path / "a.png"
    Image.new("RGB", (3000, 1000), "white").save(img)
    seen = {}

    def ok(**kw):
        seen.update(kw)
        return SimpleNamespace(text='{"ok": true}', candidates=[])

    p = GeminiProvider("x" * 39)
    p.client = SimpleNamespace(models=SimpleNamespace(generate_content=ok))
    req = ProviderRequest("read", "gemini-x", "s", "u", [ImagePart("FRAME F1", img)])
    assert p.generate(req) == '{"ok": true}'
    assert seen["model"] == "gemini-x"
