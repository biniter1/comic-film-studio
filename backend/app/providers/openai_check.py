"""Cheap connectivity/key check for OpenAI-compatible providers."""

from dataclasses import dataclass

import httpx


@dataclass
class CheckResult:
    ok: bool
    message_vi: str
    model: str | None = None


def check_openai_key(base_url: str, api_key: str, auth_header: str, model: str) -> CheckResult:
    """Send a short 'Trả lời OK' test request to verify connectivity and credentials."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if auth_header.lower() in ("authorization-bearer", "authorization_bearer", "bearer"):
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["x-api-key"] = api_key

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Trả lời OK"}],
        "max_tokens": 10,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException:
        return CheckResult(
            False,
            "Hết thời gian chờ khi kết nối tới cổng OpenAI Compat (timeout)",
            model,
        )
    except Exception as e:
        return CheckResult(
            False,
            f"Không kết nối được tới cổng OpenAI Compat ({type(e).__name__})",
            model,
        )

    if resp.status_code == 200:
        return CheckResult(True, f"Kết nối thành công — OpenAI Compat sẵn sàng ({model})", model)
    if resp.status_code in (401, 403):
        return CheckResult(False, "API key không hợp lệ", model)
    if resp.status_code == 402:
        return CheckResult(False, "Hết credit, nạp thêm ở cổng API", model)
    if resp.status_code == 404:
        return CheckResult(
            False, f"Không tìm thấy model '{model}' hoặc đường dẫn API không đúng", model
        )

    err_text = ""
    try:
        d = resp.json()
        err_text = str(d.get("error", {}).get("message") or d)
    except Exception:
        err_text = resp.text
    return CheckResult(False, f"Lỗi từ cổng API ({resp.status_code}): {err_text[:100]}", model)
