import json

import pytest
from fastapi.testclient import TestClient

from app.api import settings as settings_api
from app.config import settings
from app.main import create_app
from app.providers.gemini_check import CheckResult


@pytest.fixture
def c():
    with TestClient(create_app()) as client:
        yield client
    settings.save_gemini_key(None)


def test_params_persist_to_settings_json(c):
    out = c.put("/api/settings", json={"job_concurrency": 3, "muse_clip_seconds": 5}).json()
    assert out["job_concurrency"] == 3
    saved = json.loads((settings.data_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved["job_concurrency"] == 3 and saved["muse_clip_seconds"] == 5
    assert "gemini_api_key" not in saved  # secrets never go into settings.json
    settings.job_concurrency = 2
    settings.load_overrides()
    assert settings.job_concurrency == 3
    c.put("/api/settings", json={"job_concurrency": 2, "muse_clip_seconds": 4})


def test_gemini_key_save_hint_and_delete(c):
    r = c.put("/api/settings/gemini-key", json={"api_key": "short"})
    assert r.status_code == 422
    key = "AIzaSyTESTTESTTESTTESTTESTTEST1234"
    out = c.put("/api/settings/gemini-key", json={"api_key": f"  {key}  "}).json()
    assert out["gemini_configured"] is True and out["gemini_key_hint"] == "…1234"
    assert key not in json.dumps(out)  # never echo the key
    assert f"GEMINI_API_KEY={key}" in (settings.data_dir / "secrets.env").read_text(encoding="utf-8")
    out = c.delete("/api/settings/gemini-key").json()
    assert out["gemini_configured"] is False


def test_gemini_key_test_endpoint(c, monkeypatch):
    assert c.post("/api/settings/gemini-key/test").status_code == 409
    c.put("/api/settings/gemini-key", json={"api_key": "AIzaSyTESTTESTTESTTESTTESTTEST1234"})
    monkeypatch.setattr(
        settings_api, "check_gemini_key", lambda k, m: CheckResult(False, "API key không hợp lệ", m)
    )
    r = c.post("/api/settings/gemini-key/test").json()
    assert r["ok"] is False and "không hợp lệ" in r["message_vi"]
