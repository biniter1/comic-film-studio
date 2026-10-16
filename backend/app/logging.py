import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SecretMaskingFilter(logging.Filter):
    PATTERNS = [
        re.compile(r"AIza[0-9A-Za-z_\-]{25,45}"),
        re.compile(r"sk-[0-9A-Za-z_\-]{20,}"),
        re.compile(
            r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{8,})['\"]?"
        ),
    ]

    def __init__(self, sensitive_tokens: list[str] | None = None) -> None:
        super().__init__()
        self.sensitive_tokens = [tok for tok in (sensitive_tokens or []) if tok]

    def mask_text(self, text: str) -> str:
        for token in self.sensitive_tokens:
            if token and token in text:
                text = text.replace(token, "****")

        for pattern in self.PATTERNS:

            def repl(m: re.Match) -> str:
                if len(m.groups()) == 2:
                    return f"{m.group(1)}=****"
                return "****"

            text = pattern.sub(repl, text)

        return text

    def filter(self, record: logging.LogRecord) -> bool:
        # Format first, then mask the final text. Converting args to str before formatting
        # breaks %-style placeholders such as "%d" (e.g. httpx/uvicorn access logs).
        try:
            message = record.getMessage()
        except Exception:  # malformed record: keep it, but never crash the logger
            message = str(record.msg)
        record.msg = self.mask_text(message)
        record.args = None
        return True


class JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(data_dir: Path, sensitive_tokens: list[str] | None = None) -> logging.Logger:
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "app.log"

    masking_filter = SecretMaskingFilter(sensitive_tokens=sensitive_tokens)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if setup called multiple times
    root_logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(masking_filter)
    root_logger.addHandler(console_handler)

    # JSON-Lines File Handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(JsonLinesFormatter())
    file_handler.addFilter(masking_filter)
    root_logger.addHandler(file_handler)

    return root_logger
