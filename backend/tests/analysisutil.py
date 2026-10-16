"""Helpers for Phase 2a tests: a chapter with approved frames + a scripted fake provider."""

import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from app.providers import registry
from app.providers.base import ProviderRequest
from app.providers.fake import FakeProvider
from tests.apiutil import new_chapter, upload, wait_job
from tests.imgutil import gutter, noise_block, page


def _png(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def chapter_with_frames(
    c: TestClient, n: int = 3, approve: bool = True
) -> tuple[str, str, list[str]]:
    """One page with n clearly separated panels → n frames (approved)."""
    pid, cid = new_chapter(c)
    parts = [gutter(30)]
    for i in range(n):
        parts += [noise_block(300, seed=100 + i), gutter(60)]
    assert upload(c, cid, [("1.png", _png(page(parts)))])["status"] == "succeeded"
    job = c.post(f"/api/chapters/{cid}/frames/auto").json()
    assert wait_job(c, job["id"])["status"] == "succeeded"
    frames = [f["id"] for f in c.get(f"/api/chapters/{cid}/frames").json()["frames"]]
    assert len(frames) == n, frames
    if approve:
        assert c.post(f"/api/chapters/{cid}/frames/approve").status_code == 200
    return pid, cid, frames


def targets_of(req: ProviderRequest) -> list[str]:
    data = json.loads(req.user_text)
    return (
        data["TARGET_FRAMES"]
        if req.stage == "read"
        else [x["line_id"] for x in data["TARGET_LINES"]]
    )


class Script:
    """Builds fake model answers.

    frames: frame_id → {"type": ..., "texts": [ReadText dicts]}
    polish: function(raw_text) → new text (dialogue stage)
    """

    def __init__(self, frames: dict[str, dict], polish=None, glossary=None, new_characters=None):
        self.frames = frames
        self.polish = polish or (lambda t: t)
        self.glossary = glossary or []
        self.new_characters = new_characters or [
            {"key": "lam_phong", "name": "Lâm Phong", "gender": "male", "age_group": "young_adult"}
        ]

    def read_answer(self, req: ProviderRequest) -> dict:
        out = []
        for fid in targets_of(req):
            spec = self.frames.get(fid, {})
            out.append(
                {
                    "frame_id": fid,
                    "frame_type": spec.get("type", "scene"),
                    "description": "a frame",
                    "texts": spec.get("texts", []),
                }
            )
        return {"frames": out, "new_characters": self.new_characters, "running_summary": "so far"}

    def dialogue_answer(self, req: ProviderRequest) -> dict:
        data = json.loads(req.user_text)
        return {
            "lines": [
                {"line_id": x["line_id"], "text": self.polish(x["text"])}
                for x in data["TARGET_LINES"]
            ],
            "glossary_candidates": self.glossary,
        }

    def __call__(self, req: ProviderRequest) -> str:
        ans = self.read_answer(req) if req.stage == "read" else self.dialogue_answer(req)
        return json.dumps(ans, ensure_ascii=False)


def use_fake(respond) -> FakeProvider:
    fake = FakeProvider(respond)
    registry.factory = lambda: fake
    return fake


def line(no: int, text: str, speaker: str | None = "lam_phong", **kw) -> dict:
    return {
        "line_no": no,
        "kind": kw.pop("kind", "dialogue"),
        "text": text,
        "speaker_key": speaker,
        "speaker_gender": "male",
        "speaker_confidence": kw.pop("conf", 0.9),
        "belongs_to": kw.pop("belongs_to", "self"),
        **kw,
    }
