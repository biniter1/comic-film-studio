import json

import pytest

from app.analysis.engine import call_structured, extract_json
from app.analysis.schemas import ReadBatchOut
from app.analysis.stages import read_validator
from app.providers.base import ProviderError, ProviderRequest
from app.providers.fake import FakeProvider

GOOD = {"frames": [{"frame_id": "F1", "frame_type": "scene"}], "running_summary": "x"}


def req(text="u"):
    return ProviderRequest(stage="read", model="m", system="sys", user_text=text)


def test_extract_json_from_fenced_and_chatty_output():
    assert extract_json('Đây:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": [1, 2]} hope it helps') == {"a": [1, 2]}


def test_invalid_then_valid_retries_with_feedback(tmp_path):
    answers = iter(["not json", json.dumps(GOOD)])
    fake = FakeProvider(lambda r: next(answers))
    obj, attempts, _ = call_structured(
        fake,
        req(),
        ReadBatchOut,
        prompt_version="v1",
        work_dir=tmp_path,
        extra_validate=read_validator(["F1"]),
    )
    assert attempts == 2 and obj.frames[0].frame_id == "F1"
    # second call carried the error back to the model
    assert fake.calls[1].history and "invalid" in fake.calls[1].history[0][1]


def test_wrong_frames_feedback_names_expected_ids(tmp_path):
    bad = {"frames": [{"frame_id": "F9", "frame_type": "scene"}]}
    answers = iter([json.dumps(bad), json.dumps(GOOD)])
    fake = FakeProvider(lambda r: next(answers))
    call_structured(
        fake,
        req(),
        ReadBatchOut,
        prompt_version="v1",
        work_dir=tmp_path,
        extra_validate=read_validator(["F1"]),
    )
    assert "F1" in fake.calls[1].history[0][1]


def test_three_failures_raise_invalid_output_and_keep_raw(tmp_path):
    fake = FakeProvider(lambda r: '{"frames": "nope"}')
    with pytest.raises(ProviderError) as e:
        call_structured(fake, req(), ReadBatchOut, prompt_version="v1", work_dir=tmp_path)
    assert e.value.category == "invalid_output"
    assert len(fake.calls) == 3
    assert len(list((tmp_path / "raw").glob("*.txt"))) == 3


def test_cache_hit_costs_no_call(tmp_path):
    fake = FakeProvider(lambda r: json.dumps(GOOD))
    call_structured(fake, req(), ReadBatchOut, prompt_version="v1", work_dir=tmp_path)
    obj, attempts, _ = call_structured(
        fake, req(), ReadBatchOut, prompt_version="v1", work_dir=tmp_path
    )
    assert attempts == 0 and len(fake.calls) == 1
    # different input → new call
    call_structured(fake, req("other"), ReadBatchOut, prompt_version="v1", work_dir=tmp_path)
    assert len(fake.calls) == 2
