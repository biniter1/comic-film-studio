"""Tests for OpenAI-compatible provider (SPEC 14): formatting, error mapping, secrets, settings."""

import base64
import json
import logging
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.jobs.registry import JobContext, current_job_ctx
from app.main import create_app
from app.providers import registry
from app.providers.base import ImagePart, ProviderError, ProviderRequest
from app.providers.openai_compat import OpenAICompatProvider


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CFS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CFS_SQLITE_URL", f"sqlite:///{tmp_path / 'cfs.db'}")
    app = create_app()
    with TestClient(app) as c:
        yield c


def _sample_png(path: Path) -> Path:
    im = Image.new("RGB", (200, 150), (100, 150, 200))
    im.save(path, "PNG")
    return path


@respx.mock
def test_openai_compat_request_format_and_parsing(tmp_path):
    img_path = _sample_png(tmp_path / "frame1.png")
    base_url = "https://revidapi.com/v1"
    key = "sk-test-secret-key-12345"

    endpoint = respx.post(f"{base_url}/chat/completions").respond(
        status_code=200,
        json={
            "id": "chatcmpl-123",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"characters": ["lam_phong"], "text": "Ta là ai?"}',
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 150,
                "completion_tokens": 40,
                "total_tokens": 190,
            },
        },
    )

    provider = OpenAICompatProvider(base_url=base_url, api_key=key, auth_header="x-api-key")

    log_lines = []
    dummy_ctx = JobContext(
        job_id="JTEST",
        payload={},
        log_file=tmp_path / "job.log",
        progress_callback=lambda p, m: None,
        cancel_check=lambda: False,
    )
    dummy_ctx.log = lambda m: log_lines.append(m)

    req = ProviderRequest(
        stage="read",
        model="gpt-4o",
        system="You are an expert comic reader.",
        user_text="Extract dialogue and speakers.",
        images=[ImagePart(label="FRAME 01 (TARGET)", path=img_path)],
        history=[
            ('{"previous": "attempt"}', "Fix formatting"),
        ],
    )

    token = current_job_ctx.set(dummy_ctx)
    try:
        result = provider.generate(req)
    finally:
        current_job_ctx.reset(token)

    assert result == '{"characters": ["lam_phong"], "text": "Ta là ai?"}'
    assert endpoint.called
    sent_request = endpoint.calls.last.request

    # Check header
    assert sent_request.headers.get("x-api-key") == key

    # Check body
    body = json.loads(sent_request.content)
    assert body["model"] == "gpt-4o"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.3

    messages = body["messages"]
    assert len(messages) == 4
    # 0: system
    assert messages[0] == {"role": "system", "content": "You are an expert comic reader."}
    # 1: user
    user_msg = messages[1]
    assert user_msg["role"] == "user"
    parts = user_msg["content"]
    assert parts[0] == {"type": "text", "text": "Extract dialogue and speakers."}
    assert parts[1] == {"type": "text", "text": "FRAME 01 (TARGET)"}
    assert parts[2]["type"] == "image_url"
    assert parts[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    # Verify base64 decode works
    b64_str = parts[2]["image_url"]["url"].split(",", 1)[1]
    raw_img = base64.b64decode(b64_str)
    assert len(raw_img) > 0

    # 2 & 3: history
    assert messages[2] == {"role": "assistant", "content": '{"previous": "attempt"}'}
    assert messages[3] == {"role": "user", "content": "Fix formatting"}

    # Check job usage logging
    assert any("prompt_tokens=150" in line and "completion_tokens=40" in line for line in log_lines)


@respx.mock
def test_openai_compat_authorization_bearer_header(tmp_path):
    base_url = "https://api.openai.com/v1"
    key = "sk-bearer-key-9999"

    endpoint = respx.post(f"{base_url}/chat/completions").respond(
        status_code=200,
        json={"choices": [{"message": {"content": '{"ok": true}'}}]},
    )

    provider = OpenAICompatProvider(
        base_url=base_url, api_key=key, auth_header="authorization-bearer"
    )
    req = ProviderRequest(
        stage="dialogue",
        model="gpt-4o-mini",
        system="System prompt",
        user_text="User text",
    )
    res = provider.generate(req)
    assert res == '{"ok": true}'
    assert endpoint.calls.last.request.headers.get("Authorization") == f"Bearer {key}"


@respx.mock
def test_openai_compat_error_mapping():
    base_url = "https://revidapi.com/v1"
    provider = OpenAICompatProvider(base_url=base_url, api_key="sk-test", auth_header="x-api-key")
    req = ProviderRequest(stage="read", model="m", system="", user_text="hi")

    # 429 -> transient
    respx.post(f"{base_url}/chat/completions").respond(status_code=429, text="Rate limit exceeded")
    with pytest.raises(ProviderError) as exc_429:
        provider.generate(req)
    assert exc_429.value.category == "transient"

    # 500 / 502 -> transient
    respx.post(f"{base_url}/chat/completions").respond(status_code=502, text="Bad Gateway")
    with pytest.raises(ProviderError) as exc_502:
        provider.generate(req)
    assert exc_502.value.category == "transient"

    # Timeout -> transient
    respx.post(f"{base_url}/chat/completions").mock(side_effect=httpx.TimeoutException("timeout"))
    with pytest.raises(ProviderError) as exc_timeout:
        provider.generate(req)
    assert exc_timeout.value.category == "transient"

    # 401 / 403 -> permanent "API key không hợp lệ"
    respx.post(f"{base_url}/chat/completions").respond(status_code=401, text="Unauthorized")
    with pytest.raises(ProviderError) as exc_401:
        provider.generate(req)
    assert exc_401.value.category == "permanent"
    assert "API key không hợp lệ" in exc_401.value.message_vi

    respx.post(f"{base_url}/chat/completions").respond(status_code=403, text="Forbidden")
    with pytest.raises(ProviderError) as exc_403:
        provider.generate(req)
    assert exc_403.value.category == "permanent"
    assert "API key không hợp lệ" in exc_403.value.message_vi

    # 402 -> quota "Hết credit, nạp thêm ở cổng API"
    respx.post(f"{base_url}/chat/completions").respond(status_code=402, text="Payment Required")
    with pytest.raises(ProviderError) as exc_402:
        provider.generate(req)
    assert exc_402.value.category == "quota"
    assert "Hết credit, nạp thêm ở cổng API" in exc_402.value.message_vi

    # Message mentions out of credit / quota -> quota
    respx.post(f"{base_url}/chat/completions").respond(
        status_code=400,
        json={"error": {"message": "You have exceeded your current quota / out of credit."}},
    )
    with pytest.raises(ProviderError) as exc_quota_msg:
        provider.generate(req)
    assert exc_quota_msg.value.category == "quota"
    assert "Hết credit, nạp thêm ở cổng API" in exc_quota_msg.value.message_vi

    # 400 with other error -> permanent with message
    respx.post(f"{base_url}/chat/completions").respond(
        status_code=400, json={"error": {"message": "Invalid temperature value"}}
    )
    with pytest.raises(ProviderError) as exc_400:
        provider.generate(req)
    assert exc_400.value.category == "permanent"
    assert "Invalid temperature value" in exc_400.value.message_vi


@respx.mock
def test_key_does_not_leak_in_logs_or_errors(caplog, tmp_path):
    secret_key = "sk-super-confidential-secret-key-xyz987"
    base_url = "https://revidapi.com/v1"
    provider = OpenAICompatProvider(base_url=base_url, api_key=secret_key, auth_header="x-api-key")

    # Success call
    respx.post(f"{base_url}/chat/completions").respond(
        status_code=200,
        json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )
    req = ProviderRequest(stage="read", model="m", system="", user_text="hi")

    job_log = tmp_path / "job.log"
    dummy_ctx = JobContext(
        job_id="JLOG",
        payload={},
        log_file=job_log,
        progress_callback=lambda p, m: None,
        cancel_check=lambda: False,
    )
    token = current_job_ctx.set(dummy_ctx)
    with caplog.at_level(logging.DEBUG):
        provider.generate(req)
    current_job_ctx.reset(token)

    assert secret_key not in caplog.text
    if job_log.exists():
        assert secret_key not in job_log.read_text(encoding="utf-8")

    # Error call
    respx.post(f"{base_url}/chat/completions").respond(
        status_code=500, text="Internal Server Error"
    )
    with pytest.raises(ProviderError) as exc_err:
        provider.generate(req)

    assert secret_key not in str(exc_err.value)
    assert secret_key not in caplog.text


@respx.mock
def test_settings_openai_key_crud_and_test(client: TestClient):
    # Initial status
    s = client.get("/api/settings").json()
    assert s["openai_configured"] is False
    assert s["openai_key_hint"] is None

    # Test without configuring key -> 409
    res_test_unconf = client.post("/api/settings/openai-key/test")
    assert res_test_unconf.status_code == 409

    # Set key
    put_res = client.put(
        "/api/settings/openai-key",
        json={"api_key": "sk-revid-1234567890abcdef"},
    )
    assert put_res.status_code == 200
    data = put_res.json()
    assert data["openai_configured"] is True
    assert data["openai_key_hint"] == "…cdef"
    # Key itself is NEVER in the response
    assert "sk-revid-1234567890abcdef" not in json.dumps(data)

    # Test key endpoint with mock
    respx.post("https://revidapi.com/v1/chat/completions").respond(
        status_code=200,
        json={"choices": [{"message": {"content": "OK"}}]},
    )
    test_res = client.post("/api/settings/openai-key/test")
    assert test_res.status_code == 200
    assert test_res.json()["ok"] is True
    assert "sẵn sàng" in test_res.json()["message_vi"]

    # Delete key
    del_res = client.delete("/api/settings/openai-key")
    assert del_res.status_code == 200
    assert del_res.json()["openai_configured"] is False
    assert del_res.json()["openai_key_hint"] is None


def test_registry_provider_selection(monkeypatch):
    monkeypatch.delenv("CFS_FAKE_PROVIDER", raising=False)
    monkeypatch.setattr(registry, "factory", registry._default)

    # When gemini
    monkeypatch.setattr(settings, "analysis_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-gemini-key")
    p1 = registry.get_provider()
    assert p1.name == "gemini"

    # When openai_compat
    monkeypatch.setattr(settings, "analysis_provider", "openai_compat")
    monkeypatch.setattr(settings, "openai_compat_api_key", "test-openai-key")
    monkeypatch.setattr(settings, "openai_base_url", "https://revidapi.com/v1")
    monkeypatch.setattr(settings, "openai_auth_header", "x-api-key")
    p2 = registry.get_provider()
    assert p2.name == "openai_compat"
    assert isinstance(p2, OpenAICompatProvider)
