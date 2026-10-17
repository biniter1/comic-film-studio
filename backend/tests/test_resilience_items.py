"""Tests for resilience items 9, 10, 11, 12, 13."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.analysis.engine import load_prompt
from app.analysis.schemas import (
    DialogueEdit,
    FrameReadingOut,
    GlossaryCandidate,
    NewCharacter,
    ReadText,
)
from app.analysis.stages import PROMPT_VERSION
from app.main import create_app
from app.providers import registry
from tests.analysisutil import chapter_with_frames


@pytest.fixture
def c():
    orig = registry.factory
    with TestClient(create_app()) as client:
        yield client
    registry.factory = orig


# ---------------------------------------------------------------------------
# Item 9 & 10: Schemas loose normalization & extra="forbid"
# ---------------------------------------------------------------------------


def test_schema_loose_normalization_and_synonyms():
    # Test ReadText loose normalization
    t1 = ReadText.model_validate(
        {
            "line_no": 1,
            "kind": " NARRATOR ",
            "text": "Một ngày nọ...",
            "speaker_gender": " MALE ",
            "speaker_age": " young adult ",
            "belongs_to": " PREVIOUS ",
        }
    )
    assert t1.kind == "narration"
    assert t1.speaker_gender == "male"
    assert t1.speaker_age == "young_adult"
    assert t1.belongs_to == "prev"

    # Test age synonyms and ""/null -> unknown
    t2 = ReadText.model_validate(
        {
            "line_no": 2,
            "kind": "thought",
            "text": "Mình phải làm sao?",
            "speaker_gender": "",
            "speaker_age": None,
        }
    )
    assert t2.kind == "inner_thought"
    assert t2.speaker_gender == "unknown"
    assert t2.speaker_age == "unknown"

    # Test more age synonyms: kid, middle-age, elder, old
    t3 = ReadText.model_validate(
        {
            "line_no": 3,
            "kind": "dialogue",
            "text": "Dạ!",
            "speaker_age": "kid",
        }
    )
    assert t3.speaker_age == "child"

    t4 = ReadText.model_validate(
        {
            "line_no": 4,
            "kind": "dialogue",
            "text": "Đứng lại!",
            "speaker_age": "middle-age",
        }
    )
    assert t4.speaker_age == "middle_aged"

    t5 = ReadText.model_validate(
        {
            "line_no": 5,
            "kind": "dialogue",
            "text": "Khụ khụ...",
            "speaker_age": "old",
        }
    )
    assert t5.speaker_age == "elderly"

    # FrameReadingOut frame_type normalization
    f = FrameReadingOut.model_validate(
        {
            "frame_id": "f1",
            "frame_type": " DIALOGUE-ONLY ",
            "description": "desc",
            "texts": [t1],
        }
    )
    assert f.frame_type == "dialogue_only"

    # GlossaryCandidate term kind normalization
    g = GlossaryCandidate.model_validate({"term": "Nguyên Linh", "kind": " TECHNIQUE "})
    assert g.kind == "technique"

    # NewCharacter normalization
    nc = NewCharacter.model_validate(
        {
            "key": "lao_gia",
            "name": "Lão Giả",
            "gender": "unknown",
            "age_group": "elder",
        }
    )
    assert nc.age_group == "elderly"

    # Invalid values still raise ValidationError
    with pytest.raises(ValidationError):
        ReadText.model_validate({"line_no": 1, "kind": "unsupported_kind", "text": "hello"})

    with pytest.raises(ValidationError):
        ReadText.model_validate(
            {"line_no": 1, "kind": "dialogue", "text": "hi", "speaker_age": "ancient_being"}
        )


def test_schema_speaker_alias_and_extra_forbid():
    # 1. "speaker" mapped to speaker_key if ^[a-z0-9_]+$
    t1 = ReadText.model_validate(
        {
            "line_no": 1,
            "kind": "dialogue",
            "text": "Xin chào",
            "speaker": "lam_phong",
        }
    )
    assert t1.speaker_key == "lam_phong"
    assert t1.speaker_label is None

    # 2. "speaker" mapped to speaker_label if not snake_case identifier
    t2 = ReadText.model_validate(
        {
            "line_no": 1,
            "kind": "dialogue",
            "text": "Xin chào",
            "speaker": "Lão Giả Áo Đen",
        }
    )
    assert t2.speaker_key is None
    assert t2.speaker_label == "Lão Giả Áo Đen"

    # 3. If speaker_key or speaker_label already present, "speaker" does not overwrite
    t3 = ReadText.model_validate(
        {
            "line_no": 1,
            "kind": "dialogue",
            "text": "Xin chào",
            "speaker_key": "existing_key",
            "speaker": "ignored_speaker",
        }
    )
    assert t3.speaker_key == "existing_key"

    # 4. extra="forbid" on ReadText
    with pytest.raises(ValidationError) as exc_t:
        ReadText.model_validate(
            {
                "line_no": 1,
                "kind": "dialogue",
                "text": "Xin chào",
                "random_extra_field": 123,
            }
        )
    assert "extra" in str(exc_t.value).lower()

    # 5. extra="forbid" on FrameReadingOut
    with pytest.raises(ValidationError):
        FrameReadingOut.model_validate(
            {
                "frame_id": "f1",
                "frame_type": "scene",
                "extra_prop": "nope",
            }
        )

    # 6. extra="forbid" on NewCharacter
    with pytest.raises(ValidationError):
        NewCharacter.model_validate(
            {
                "key": "char_1",
                "name": "Char 1",
                "extra_prop": "nope",
            }
        )

    # 7. extra="forbid" on DialogueEdit
    with pytest.raises(ValidationError):
        DialogueEdit.model_validate(
            {
                "line_id": "l1",
                "text": "text",
                "extra_prop": "nope",
            }
        )


# ---------------------------------------------------------------------------
# Item 11: Prompts v2
# ---------------------------------------------------------------------------


def test_prompts_v2():
    assert PROMPT_VERSION == "v2"
    read_p = load_prompt("read", "v2")
    assert "frame_type" in read_p
    assert "Full JSON Output Example:" in read_p
    assert '"frames": [' in read_p

    dial_p = load_prompt("dialogue", "v2")
    assert (
        "Chữ trong truyện thường viết IN HOA — chuyển về chữ thường đúng chính tả tiếng Việt"
        in dial_p
    )
    assert "Ví dụ JSON trả về đầy đủ:" in dial_p
    assert '"lines": [' in dial_p


def test_prompts_dialogue_v3():
    from app.analysis.stages import PROMPT_VERSION_DIALOGUE

    assert PROMPT_VERSION_DIALOGUE == "v3"
    dial_p = load_prompt("dialogue", "v3")
    assert "uncertain" in dial_p
    assert "TUYỆT ĐỐI KHÔNG ghi edit_note" in dial_p
    assert '"uncertain": true' in dial_p


# ---------------------------------------------------------------------------
# Item 12: Manual bundles JPEG conversion and HUONG_DAN.txt
# ---------------------------------------------------------------------------


def test_manual_bundle_jpeg_conversion(c):
    pid, cid, frames = chapter_with_frames(c, n=2)
    prep = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "manual"}).json()
    assert len(prep["units"]) >= 1

    bundle_res = c.get(f"/api/chapters/{cid}/analysis/read/bundle?unit=0")
    assert bundle_res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(bundle_res.content))
    names = zf.namelist()

    # Check HUONG_DAN.txt first line
    readme = zf.read("HUONG_DAN.txt").decode("utf-8")
    assert readme.startswith(
        "Giải nén (Extract All) trước khi kéo ảnh vào Gemini — "
        "kéo thẳng từ file zip sẽ bị lỗi tải lên. Mỗi gói dùng một cuộc chat MỚI."
    )

    # Check images are .jpg and valid JPEG
    img_names = [n for n in names if n.startswith("images/")]
    assert len(img_names) == 2
    for img_name in img_names:
        assert img_name.endswith(".jpg")
        img_bytes = zf.read(img_name)
        with Image.open(io.BytesIO(img_bytes)) as im:
            assert im.format == "JPEG"
            assert max(im.size) <= 1600


# ---------------------------------------------------------------------------
# Item 13: Manual paste auto-detect, redirection, and 422 unmatched
# ---------------------------------------------------------------------------


def test_manual_paste_auto_detect_and_redirect(c):
    # Create chapter with 6 frames -> split into 1 batch of 6
    pid, cid, frames = chapter_with_frames(c, n=3)
    c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "manual"})

    # 1. Unmatched targets -> 422 with expected frame_ids
    bad_json = json.dumps(
        {
            "frames": [
                {
                    "frame_id": "non_existent_frame",
                    "frame_type": "scene",
                    "description": "",
                    "characters": [],
                    "texts": [],
                }
            ],
            "new_characters": [],
            "running_summary": "",
        }
    )
    bad_res = c.post(f"/api/chapters/{cid}/analysis/read/paste", json={"raw": bad_json})
    assert bad_res.status_code == 422
    err_body = bad_res.json()["error"]
    assert err_body["code"] == "UNMATCHED_TARGETS"
    assert frames[0] in err_body["message_vi"]

    # 2. Omitted unit_index -> auto matches unit 0
    good_data = {
        "frames": [
            {
                "frame_id": fid,
                "frame_type": "scene",
                "description": "scene",
                "characters": [],
                "texts": [{"line_no": 1, "kind": "dialogue", "text": "Alo"}],
            }
            for fid in frames
        ],
        "new_characters": [],
        "running_summary": "summary",
    }
    good_json = json.dumps(good_data)
    auto_res = c.post(
        f"/api/chapters/{cid}/analysis/read/paste",
        json={"raw": good_json},  # unit_index is omitted!
    )
    assert auto_res.status_code == 200
    res_data = auto_res.json()
    assert res_data["matched_unit"] == 0
    assert "Đã áp dụng" in res_data["message_vi"]


def test_manual_paste_redirect_when_different_slot_selected(c):
    # 7 frames: unit 0 has 6 frames, unit 1 has 1 frame
    pid, cid, frames = chapter_with_frames(c, n=7)
    c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "manual"})

    # Prepare data matching unit 1 (frames[6:])
    unit1_data = {
        "frames": [
            {
                "frame_id": frames[6],
                "frame_type": "scene",
                "description": "last frame",
                "characters": [],
                "texts": [{"line_no": 1, "kind": "dialogue", "text": "Hết"}],
            }
        ],
        "new_characters": [],
        "running_summary": "sum",
    }
    unit1_json = json.dumps(unit1_data)

    # User accidentally pastes in slot 0 (unit_index = 0)
    res = c.post(
        f"/api/chapters/{cid}/analysis/read/paste",
        json={"unit_index": 0, "raw": unit1_json},
    )
    assert res.status_code == 200
    data = res.json()
    # It redirects to unit 1 (display "gói 2")
    assert data["matched_unit"] == 1
    assert "Kết quả thuộc gói 2, đã tự chuyển" in data["message_vi"]
