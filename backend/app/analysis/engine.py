"""Structured calls: JSON extraction, schema validation, feedback-retry, cache (SPEC §4.1)."""

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.providers.base import AnalysisProvider, ProviderError, ProviderRequest

T = TypeVar("T", bound=BaseModel)
PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_ATTEMPTS = 3


def load_prompt(stage: str, version: str = "v2") -> str:
    return (PROMPTS_DIR / f"{stage}.{version}.md").read_text(encoding="utf-8")


def extract_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        if not starts:
            raise
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start : end + 1])


def request_hash(req: ProviderRequest, prompt_version: str) -> str:
    h = hashlib.sha256()
    for part in (req.stage, req.model, prompt_version, req.system, req.user_text):
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    for img in req.images:
        h.update(img.label.encode("utf-8"))
        h.update(hashlib.sha256(img.path.read_bytes()).digest())
    return h.hexdigest()


def parse_and_validate(raw: str, schema: type[T], extra: Callable[[T], None] | None = None) -> T:
    """Raise ValueError with a model-readable message when invalid."""
    try:
        data = extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Output is not valid JSON: {e}") from e
    try:
        obj = schema.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"JSON does not match the schema:\n{e}") from e
    if extra:
        extra(obj)
    return obj


def call_structured(
    provider: AnalysisProvider,
    req: ProviderRequest,
    schema: type[T],
    *,
    prompt_version: str,
    work_dir: Path,
    extra_validate: Callable[[T], None] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> tuple[T, int, str]:
    """Return (parsed, attempts, input_hash). Raw outputs are always kept under work_dir/raw/.
    A successful raw output is cached by input hash so re-running costs no quota."""
    raw_dir = work_dir / "raw"
    cache_dir = work_dir / "cache"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    ih = request_hash(req, prompt_version)
    cached = cache_dir / f"{ih}.json"
    if cached.exists():
        try:
            return (
                parse_and_validate(cached.read_text(encoding="utf-8"), schema, extra_validate),
                0,
                ih,
            )
        except ValueError:
            cached.unlink(missing_ok=True)

    history: list[tuple[str, str]] = []
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        raw = provider.generate(
            ProviderRequest(
                req.stage, req.model, req.system, req.user_text, req.images, list(history)
            )
        )
        (raw_dir / f"{req.stage}_{ih[:12]}_try{attempt}.txt").write_text(raw, encoding="utf-8")
        try:
            obj = parse_and_validate(raw, schema, extra_validate)
        except ValueError as e:
            last_error = str(e)[:4000]
            history.append(
                (
                    raw,
                    "Your previous answer was invalid:\n"
                    + last_error
                    + "\nReturn the COMPLETE corrected JSON only, no explanations.",
                )
            )
            continue
        cached.write_text(raw, encoding="utf-8")
        return obj, attempt, ih
    raise ProviderError(
        "invalid_output",
        f"AI trả kết quả sai định dạng sau {max_attempts} lần thử: {last_error[:300]}",
        "Xem output gốc trong thư mục analysis/raw, thử lại hoặc dùng chế độ thủ công",
    )
