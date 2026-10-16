"""Client LLM tương thích OpenAI (Muse Spark, Gemini OpenAI-compat, OpenRouter...).

- Gửi ảnh dạng data URI.
- Ép trả JSON, tự sửa lỗi: nếu JSON sai schema, gửi lại lỗi validate cho model sửa (tối đa N lần).
- Cache theo hash prompt để chạy lại không tốn token.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from PIL import Image
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def image_data_uri(path: str | Path, max_side: int = 1280) -> str:
    im = Image.open(path).convert("RGB")
    s = max(im.size)
    if s > max_side:
        im = im.resize((round(im.width * max_side / s), round(im.height * max_side / s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def extract_json(text: str) -> Any:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # lấy khối {...} hoặc [...] ngoài cùng
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        if not starts:
            raise
        s = min(starts)
        e = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[s:e + 1])


class LLM:
    def __init__(self, cfg: dict, cache_dir: Optional[Path] = None):
        from openai import OpenAI  # import trễ để các lệnh khác không cần gói này

        key = os.environ.get(cfg.get("api_key_env", "MUSE_API_KEY"))
        if not key:
            raise SystemExit(f"Thiếu API key: export {cfg.get('api_key_env')}=...")
        self.client = OpenAI(base_url=cfg["base_url"], api_key=key)
        self.model = cfg["model"]
        self.temperature = cfg.get("temperature", 0.4)
        self.max_retries = cfg.get("max_retries", 3)
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _chat(self, messages: list[dict]) -> str:
        key = hashlib.sha256(json.dumps([self.model, messages], ensure_ascii=False).encode()).hexdigest()[:24]
        if self.cache_dir and (self.cache_dir / f"{key}.txt").exists():
            return (self.cache_dir / f"{key}.txt").read_text("utf-8")
        kwargs: dict = dict(model=self.model, messages=messages, temperature=self.temperature)
        try:
            resp = self.client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
        except Exception:  # endpoint không hỗ trợ json mode -> gọi thường
            resp = self.client.chat.completions.create(**kwargs)
        out = resp.choices[0].message.content or ""
        if self.cache_dir:
            (self.cache_dir / f"{key}.txt").write_text(out, "utf-8")
        return out

    def json(self, system: str, user_text: str, images: list[str | Path] = (),
             model: type[T] | None = None, post: Callable[[Any], Any] | None = None) -> Any:
        content: list[dict] = [{"type": "text", "text": user_text}]
        for p in images:
            content.append({"type": "image_url", "image_url": {"url": image_data_uri(p)}})
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        last_err = ""
        for attempt in range(self.max_retries):
            raw = self._chat(messages)
            try:
                data = extract_json(raw)
                if post:
                    data = post(data)
                return model.model_validate(data) if model else data
            except (json.JSONDecodeError, ValidationError, ValueError, KeyError, TypeError) as e:
                last_err = str(e)[:3000]
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": "JSON chưa hợp lệ với schema. Lỗi:\n" + last_err +
                     "\nHãy trả lại TOÀN BỘ JSON đã sửa, không giải thích."},
                ]
        raise RuntimeError(f"LLM không trả JSON hợp lệ sau {self.max_retries} lần: {last_err}")
