"""Cheap Gemini connectivity/key check used by the Settings page."""

from dataclasses import dataclass


@dataclass
class CheckResult:
    ok: bool
    message_vi: str
    model: str | None = None


def check_gemini_key(api_key: str, model: str) -> CheckResult:
    """Fetch model metadata (no generation → no quota spent on tokens)."""
    try:
        from google import genai
        from google.genai import errors as genai_errors
    except ImportError:  # pragma: no cover
        return CheckResult(False, "Thiếu thư viện google-genai (chạy lại: uv sync)")
    try:
        client = genai.Client(api_key=api_key)
        m = client.models.get(model=model)
        return CheckResult(True, f"Kết nối thành công — model {m.name or model} sẵn sàng", model)
    except genai_errors.ClientError as e:
        code = getattr(e, "code", None)
        if code in (400, 401, 403):
            return CheckResult(False, "API key không hợp lệ hoặc chưa được bật Gemini API", model)
        if code == 404:
            return CheckResult(False, f"Key hợp lệ nhưng không tìm thấy model '{model}'", model)
        if code == 429:
            return CheckResult(False, "Key hợp lệ nhưng đang bị giới hạn lượt gọi (429)", model)
        return CheckResult(False, f"Gemini trả lỗi {code}", model)
    except genai_errors.ServerError:
        return CheckResult(False, "Máy chủ Gemini đang lỗi, thử lại sau", model)
    except Exception as e:  # network / DNS / proxy
        return CheckResult(False, f"Không kết nối được tới Gemini ({type(e).__name__})", model)
