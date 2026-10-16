import json
from pathlib import Path

from app.logging import SecretMaskingFilter, setup_logging


def test_secret_masking_filter_google_key():
    f = SecretMaskingFilter()
    msg = "Connecting to Gemini with key AIzaSyD1234567890abcdefghijklmnopqrstuv"
    masked = f.mask_text(msg)
    assert "AIzaSyD" not in masked
    assert "****" in masked


def test_secret_masking_filter_openai_key():
    f = SecretMaskingFilter()
    msg = "Using OpenAI key sk-abcdef1234567890abcdef1234567890 for testing"
    masked = f.mask_text(msg)
    assert "sk-abcdef" not in masked
    assert "****" in masked


def test_secret_masking_filter_custom_token():
    f = SecretMaskingFilter(sensitive_tokens=["my_custom_secret_token_123"])
    msg = "Config loaded: my_custom_secret_token_123"
    masked = f.mask_text(msg)
    assert "my_custom_secret_token_123" not in masked
    assert "****" in masked


def test_setup_logging_writes_json_lines(tmp_path: Path):
    logger = setup_logging(tmp_path, sensitive_tokens=["my_secret_token"])
    logger.info(
        "Test log message with key AIzaSyD1234567890abcdefghijklmnopqrstuv and my_secret_token"
    )

    log_file = tmp_path / "logs" / "app.log"
    assert log_file.exists()

    content = log_file.read_text(encoding="utf-8").strip()
    assert content
    record = json.loads(content.splitlines()[-1])
    assert record["level"] == "INFO"
    assert "AIzaSyD" not in record["message"]
    assert "my_secret_token" not in record["message"]
    assert "****" in record["message"]


def test_masking_keeps_percent_d_placeholders_working():
    """Regression: masking must not turn int args into str before %d formatting."""
    import logging

    from app.logging import SecretMaskingFilter

    rec = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "HTTP %s %d key=%s", ("GET", 200, "AIza" + "A" * 35), None
    )
    assert SecretMaskingFilter().filter(rec)
    out = rec.getMessage()
    assert out.startswith("HTTP GET 200")
    assert "AIza" not in out
