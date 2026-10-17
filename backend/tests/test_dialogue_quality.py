"""Tests for dialogue quality: speaker validation using conversation logic (vocative conflict),
saving AI speaker suggestions, and applying speaker suggestions via API."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import db
from app.analysis import stages
from app.analysis.schemas import DialogueEdit, DialogueOut
from app.main import create_app
from app.models.analysis import Character, DialogueLine
from app.providers import registry
from app.providers.fake import FakeProvider
from tests.analysisutil import chapter_with_frames
from tests.apiutil import wait_job


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CFS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CFS_SQLITE_URL", f"sqlite:///{tmp_path / 'cfs.db'}")
    orig = registry.factory
    app = create_app()
    with TestClient(app) as c:
        yield c
    registry.factory = orig


# ---------------------------------------------------------------------------
# 1. Hô ngữ "Đồ trưởng lão, ..." với speaker do_truong_lao -> needs_review + suggestion
# ---------------------------------------------------------------------------
def test_vocative_speaker_conflict_flags_review_and_suggestion(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=1)
    fid = frames[0]

    with Session(db.engine) as s:
        char = Character(
            project_id=pid,
            key="do_truong_lao",
            name="Đồ Trưởng Lão",
            aliases=["Đồ trưởng lão"],
        )
        line = DialogueLine(
            chapter_id=cid,
            source_frame_id=fid,
            order=1,
            speaker_key="do_truong_lao",
            speaker_label="Đồ trưởng lão",
            speaker_confidence=0.9,
            text_raw="Đồ trưởng lão, ngươi hãy nhận lấy cái chết!",
            text="Đồ trưởng lão, ngươi hãy nhận lấy cái chết!",
        )
        s.add_all([char, line])
        s.commit()
        lid = line.id

    out = DialogueOut(
        lines=[
            DialogueEdit(
                line_id=lid,
                text="Đồ trưởng lão, ngươi hãy nhận lấy cái chết!",
                edit_note=None,
            )
        ]
    )

    stages.apply_dialogue_unit(cid, 0, out, mode="api", attempts=1, ih=None)

    with Session(db.engine) as s:
        d = s.get(DialogueLine, lid)
        assert d is not None
        assert d.needs_review is True
        assert d.speaker_suggestion is not None
        assert d.speaker_suggestion.get("reason") == "Câu gọi tên chính người nói"
        # KHÔNG tự đổi speaker
        assert d.speaker_key == "do_truong_lao"


def test_vocative_speaker_conflict_with_various_punctuations(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=1)
    fid = frames[0]

    with Session(db.engine) as s:
        char = Character(
            project_id=pid,
            key="do_truong_lao",
            name="Đồ Trưởng Lão",
        )
        line = DialogueLine(
            chapter_id=cid,
            source_frame_id=fid,
            order=1,
            speaker_key="do_truong_lao",
            speaker_label="Đồ trưởng lão",
            text_raw="Đồ trưởng lão! Cẩn thận!",
            text="Đồ trưởng lão! Cẩn thận!",
        )
        s.add_all([char, line])
        s.commit()
        lid = line.id

    out = DialogueOut(
        lines=[
            DialogueEdit(
                line_id=lid,
                text="Đồ trưởng lão! Cẩn thận!",
                edit_note=None,
            )
        ]
    )

    stages.apply_dialogue_unit(cid, 0, out, mode="api", attempts=1, ih=None)

    with Session(db.engine) as s:
        d = s.get(DialogueLine, lid)
        assert d is not None
        assert d.needs_review is True
        assert d.speaker_suggestion is not None
        assert d.speaker_suggestion.get("reason") == "Câu gọi tên chính người nói"


# ---------------------------------------------------------------------------
# 2. speaker_suggestion từ provider giả được lưu và áp dụng qua API
# ---------------------------------------------------------------------------
def test_speaker_suggestion_saved_and_applied_via_api(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=1)
    fid = frames[0]

    with Session(db.engine) as s:
        c1 = Character(
            project_id=pid,
            key="lam_phong",
            name="Lâm Phong",
            gender="male",
            age_group="young_adult",
        )
        c2 = Character(
            project_id=pid,
            key="chuc_vu_phi",
            name="Chúc Vũ Phi",
            gender="female",
            age_group="young_adult",
        )
        line = DialogueLine(
            chapter_id=cid,
            source_frame_id=fid,
            order=1,
            speaker_key="lam_phong",
            speaker_label="Lâm Phong",
            speaker_confidence=0.8,
            text_raw="Lâm Phong, ta nhất định sẽ báo thù!",
            text="Lâm Phong, ta nhất định sẽ báo thù!",
            needs_review=False,
            reviewed=False,
        )
        ch = s.get(stages.Chapter, cid)
        ch.status = "dialogue_draft"
        s.add_all([ch, c1, c2, line])
        s.commit()
        lid = line.id

    # 1. Fake provider returns speaker_suggestion proposing chuc_vu_phi
    dialogue_response = {
        "lines": [
            {
                "line_id": lid,
                "text": "Lâm Phong, ta nhất định sẽ báo thù!",
                "edit_note": None,
                "uncertain": False,
                "speaker_suggestion": {
                    "speaker_key": "chuc_vu_phi",
                    "speaker_label": "Chúc Vũ Phi",
                    "reason": "Câu này người nói đe dọa Lâm Phong, phải là Chúc Vũ Phi",
                },
            }
        ],
        "glossary_candidates": [],
        "address_candidates": [],
    }

    def respond(req):
        if req.stage == "dialogue":
            return json.dumps(dialogue_response, ensure_ascii=False)
        raise ValueError(f"unexpected stage: {req.stage}")

    registry.factory = lambda: FakeProvider(respond)

    # Run dialogue stage
    r = client.post(f"/api/chapters/{cid}/analysis/dialogue", json={"mode": "api"})
    assert r.status_code == 200
    for j in r.json()["jobs"]:
        wait_job(client, j["id"])

    # 2. Check line in DB: speaker_suggestion is stored, speaker is NOT yet changed
    with Session(db.engine) as s:
        d = s.get(DialogueLine, lid)
        assert d is not None
        assert d.needs_review is True
        assert d.speaker_key == "lam_phong"  # unchanged
        assert d.speaker_suggestion is not None
        assert d.speaker_suggestion["speaker_key"] == "chuc_vu_phi"
        assert d.speaker_suggestion["speaker_label"] == "Chúc Vũ Phi"

    # Also verify via GET /api/chapters/{cid}/dialogue
    diag_data = client.get(f"/api/chapters/{cid}/dialogue").json()
    diag_line = next(x for x in diag_data["lines"] if x["id"] == lid)
    assert diag_line["speaker_suggestion"] is not None
    assert diag_line["speaker_suggestion"]["speaker_key"] == "chuc_vu_phi"

    # 3. Apply suggestion via API POST /api/dialogue/{lid}/apply-speaker-suggestion
    apply_res = client.post(f"/api/dialogue/{lid}/apply-speaker-suggestion")
    assert apply_res.status_code == 200
    applied_data = apply_res.json()
    assert applied_data["speaker_key"] == "chuc_vu_phi"
    assert applied_data["speaker_label"] == "Chúc Vũ Phi"
    assert applied_data["speaker_gender"] == "female"
    assert applied_data["speaker_confidence"] == 1.0
    assert applied_data["speaker_suggestion"] is None
    assert applied_data["reviewed"] is True

    # 4. Applying again returns 400 NO_SUGGESTION
    apply_again = client.post(f"/api/dialogue/{lid}/apply-speaker-suggestion")
    assert apply_again.status_code == 400
    assert apply_again.json()["error"]["code"] == "NO_SUGGESTION"
