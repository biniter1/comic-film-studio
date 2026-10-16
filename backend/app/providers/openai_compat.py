"""OpenAI-compatible provider adapter (e.g. revidapi.com, OpenRouter, vLLM)."""

import base64
import json
import logging
import re
from typing import Any

import httpx

from app.jobs.registry import current_job_ctx
from app.providers.base import ProviderError, ProviderRequest
from app.providers.gemini import _jpeg_bytes

logger = logging.getLogger(__name__)


def classify_openai_error(status_code: int | None, response_text: str) -> ProviderError:
    msg = response_text or ""
    err_msg = ""
    try:
        data = json.loads(msg)
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                err_msg = str(err.get("message") or err)
            else:
                err_msg = str(err or data)
    except Exception:
        err_msg = msg

    # Quota / Credit check
    if status_code == 402 or re.search(
        r"credit|quota|balance|insufficient|nạp thêm|hết tiền", err_msg, re.I
    ):
        return ProviderError(
            "quota",
            "Hết credit, nạp thêm ở cổng API",
            "Nạp thêm credit tại cổng API hoặc đổi nhà cung cấp",
        )

    if status_code == 429:
        return ProviderError(
            "transient",
            "OpenAI Compat đang giới hạn tốc độ (429), sẽ thử lại",
        )

    if status_code in (401, 403):
        return ProviderError(
            "permanent",
            "API key không hợp lệ",
            "Kiểm tra key ở Cài đặt",
        )

    if status_code and status_code >= 500:
        return ProviderError(
            "transient",
            f"Máy chủ OpenAI Compat lỗi ({status_code}), sẽ thử lại",
        )

    if status_code == 400:
        return ProviderError(
            "permanent",
            f"OpenAI Compat từ chối yêu cầu (400): {err_msg[:200]}",
        )

    return ProviderError("transient", f"Lỗi từ OpenAI Compat ({status_code}): {err_msg[:200]}")


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        auth_header: str = "x-api-key",
    ):
        if not api_key:
            raise ProviderError(
                "permanent", "Chưa có API key OpenAI Compat", "Nhập key ở trang Cài đặt"
            )
        self.base_url = (base_url or "https://revidapi.com/v1").rstrip("/")
        self.api_key = api_key
        self.auth_header = auth_header or "x-api-key"

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.auth_header.lower() in ("authorization-bearer", "authorization_bearer", "bearer"):
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers["x-api-key"] = self.api_key
        return headers

    def generate(self, req: ProviderRequest) -> str:
        messages: list[dict[str, Any]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})

        user_content: list[dict[str, Any]] = [{"type": "text", "text": req.user_text}]
        for img in req.images:
            user_content.append({"type": "text", "text": img.label})
            b64_data = base64.b64encode(_jpeg_bytes(img.path)).decode("ascii")
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"},
                }
            )
        messages.append({"role": "user", "content": user_content})

        for output, feedback in req.history:
            messages.append({"role": "assistant", "content": output})
            messages.append({"role": "user", "content": feedback})

        payload = {
            "model": req.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }

        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=180.0) as client:
                resp = client.post(url, headers=self._get_headers(), json=payload)
        except httpx.TimeoutException as e:
            raise ProviderError(
                "transient",
                "Hết thời gian chờ phản hồi từ OpenAI Compat (timeout), sẽ thử lại",
            ) from e
        except Exception as e:
            raise ProviderError(
                "transient",
                f"Lỗi mạng khi gọi OpenAI Compat ({type(e).__name__})",
            ) from e

        if resp.status_code != 200:
            raise classify_openai_error(resp.status_code, resp.text)

        try:
            data = resp.json()
        except Exception as e:
            raise ProviderError(
                "invalid_output",
                f"OpenAI Compat trả về phản hồi không phải JSON: {resp.text[:200]}",
            ) from e

        usage = data.get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        log_msg = (
            f"OpenAICompat usage: prompt_tokens={prompt_tokens}, "
            f"completion_tokens={completion_tokens}"
        )
        ctx = current_job_ctx.get()

        if ctx:
            ctx.log(log_msg)
        logger.info(log_msg)

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("invalid_output", "OpenAI Compat không trả về choices nào")
        content = choices[0].get("message", {}).get("content")
        if not content:
            raise ProviderError("invalid_output", "OpenAI Compat trả về content rỗng")
        return content
