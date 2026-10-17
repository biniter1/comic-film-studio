"""Gemini adapter (google-genai SDK)."""

import re

from app.frames.images import _jpeg_bytes
from app.providers.base import ProviderError, ProviderRequest

DAILY_QUOTA_HINT = (
    "Đã dùng hết hạn mức trong ngày của API key. Vui lòng đổi API key khác "
    "trong Cài đặt, dùng chế độ thủ công hoặc chờ đến ngày mai (Google reset lúc 14:00 giờ VN)."
)


def classify_client_error(code: int | None, message: str) -> ProviderError:
    msg = message or ""
    if code == 429 or "RESOURCE_EXHAUSTED" in msg:
        daily_pat = r"per ?day|PerDay|daily|quota.*exceeded.*(day|free)|quota_exceeded|day_limit"
        if re.search(daily_pat, msg, re.I):
            return ProviderError(
                "quota", "Đã dùng hết hạn mức trong ngày của API key", DAILY_QUOTA_HINT
            )
        return ProviderError("transient", "Gemini đang giới hạn tốc độ (429), sẽ thử lại")
    if code in (500, 502, 503, 504):
        return ProviderError("transient", f"Máy chủ Gemini lỗi ({code}), sẽ thử lại")
    if code in (401, 403):
        return ProviderError(
            "permanent",
            "API key Gemini không hợp lệ hoặc chưa bật Gemini API",
            "Kiểm tra key ở Cài đặt",
        )
    if code == 404:
        return ProviderError(
            "permanent", "Không tìm thấy model Gemini đã cấu hình", "Đổi model ở Cài đặt"
        )
    if code == 400:
        return ProviderError("permanent", f"Gemini từ chối yêu cầu: {msg[:200]}")
    return ProviderError("transient", f"Gemini lỗi {code}: {msg[:200]}")


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str | None):
        if not api_key:
            raise ProviderError("permanent", "Chưa có API key Gemini", "Nhập key ở trang Cài đặt")
        from google import genai

        self._genai = genai
        self.client = genai.Client(api_key=api_key)

    def _generate_once(self, req: ProviderRequest) -> str:
        from google.genai import errors, types

        parts: list = [types.Part.from_text(text=req.user_text)]
        for img in req.images:
            parts.append(types.Part.from_text(text=img.label))
            parts.append(types.Part.from_bytes(data=_jpeg_bytes(img.path), mime_type="image/jpeg"))
        contents = [types.Content(role="user", parts=parts)]
        for output, feedback in req.history:
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=output)]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=feedback)]))
        config = types.GenerateContentConfig(
            system_instruction=req.system,
            response_mime_type="application/json",
            temperature=0.3,
        )
        try:
            resp = self.client.models.generate_content(
                model=req.model, contents=contents, config=config
            )
        except errors.ClientError as e:
            raise classify_client_error(getattr(e, "code", None), str(e)) from e
        except errors.ServerError as e:
            raise ProviderError("transient", "Máy chủ Gemini lỗi, sẽ thử lại") from e
        except Exception as e:  # network
            raise ProviderError("transient", f"Lỗi mạng khi gọi Gemini ({type(e).__name__})") from e
        text = getattr(resp, "text", None)
        if not text:
            reason = ""
            try:
                reason = str(resp.candidates[0].finish_reason)
            except Exception:
                pass
            raise ProviderError("invalid_output", f"Gemini không trả nội dung {reason}".strip())
        return text

    def generate(self, req: ProviderRequest) -> str:
        from app.providers.retry import call_with_retry

        return call_with_retry(lambda: self._generate_once(req), provider_name="Gemini")
