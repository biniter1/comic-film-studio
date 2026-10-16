import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import registry
from app.providers.base import ProviderError, ProviderRequest
from tests.analysisutil import Script, chapter_with_frames, line, use_fake
from tests.apiutil import wait_job


@pytest.fixture
def c():
    orig = registry.factory
    with TestClient(create_app()) as client:
        yield client
    registry.factory = orig


def prompt_input(prompt: str) -> dict:
    body = prompt.split("=== INPUT ===\n", 1)[1]
    return json.loads(body[: body.index("\n}\n") + 2])


def test_manual_read_then_dialogue_end_to_end(c):
    pid, cid, frames = chapter_with_frames(c)
    script = Script(
        {
            frames[0]: {"texts": [line(1, "Ngươi là ai?")]},
            frames[1]: {
                "type": "dialogue_only",
                "texts": [line(1, "Ta là ta.", belongs_to="next")],
            },
        },
        polish=lambda t: t.upper(),
    )

    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "manual"})
    assert r.status_code == 200, r.text
    units = r.json()["units"]
    assert [u["status"] for u in units] == ["awaiting_paste"]  # 3 frames → 1 batch

    z = c.get(f"/api/chapters/{cid}/analysis/read/bundle?unit=0")
    assert z.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    names = zf.namelist()
    assert "prompt.txt" in names and "HUONG_DAN.txt" in names
    assert len([n for n in names if n.startswith("images/")]) == 3
    prompt = zf.read("prompt.txt").decode("utf-8")
    data = prompt_input(prompt)
    assert data["TARGET_FRAMES"] == frames

    # wrong JSON → 422 with the reason
    bad = c.post(
        f"/api/chapters/{cid}/analysis/read/paste",
        json={"unit_index": 0, "raw": '{"frames": [{"frame_id": "nope", "frame_type": "scene"}]}'},
    )
    assert bad.status_code == 422 and frames[0] in bad.json()["error"]["details"]["error"]
    assert c.get(f"/api/chapters/{cid}/analysis/read/units").json()[0]["error"]

    req = ProviderRequest("read", "m", "", json.dumps(data))
    ok = c.post(
        f"/api/chapters/{cid}/analysis/read/paste",
        json={"unit_index": 0, "raw": "Kết quả:\n```json\n" + script(req) + "\n```"},
    )
    assert ok.status_code == 200, ok.text
    d = c.get(f"/api/chapters/{cid}/dialogue").json()
    assert d["status"] == "dialogue_draft"
    assert [x["anchor_frame_id"] for x in d["lines"]] == [frames[0], frames[2]]

    # dialogue stage, manual
    units = c.post(f"/api/chapters/{cid}/analysis/dialogue", json={"mode": "manual"}).json()[
        "units"
    ]
    assert len(units) == 1
    zf = zipfile.ZipFile(io.BytesIO(c.get(f"/api/chapters/{cid}/analysis/dialogue/bundle").content))
    assert not [n for n in zf.namelist() if n.startswith("images/")]
    data = prompt_input(zf.read("prompt.txt").decode("utf-8"))
    req = ProviderRequest("dialogue", "m", "", json.dumps(data))
    ok = c.post(
        f"/api/chapters/{cid}/analysis/dialogue/paste", json={"unit_index": 0, "raw": script(req)}
    )
    assert ok.status_code == 200
    texts = [x["text"] for x in c.get(f"/api/chapters/{cid}/dialogue").json()["lines"]]
    assert texts == ["NGƯƠI LÀ AI?", "TA LÀ TA."]


def test_same_result_as_api_mode(c):
    _, cid_a, fa = chapter_with_frames(c)
    _, cid_m, fm = chapter_with_frames(c)

    def specs(f):
        return {f[1]: {"type": "dialogue_only", "texts": [line(1, "Hừ.", belongs_to="prev")]}}

    use_fake(Script({**specs(fa), **specs(fm)}))
    r = c.post(f"/api/chapters/{cid_a}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert wait_job(c, r.json()["jobs"][0]["id"])["status"] == "succeeded"

    c.post(f"/api/chapters/{cid_m}/analysis/read", json={"mode": "manual"})
    zf = zipfile.ZipFile(io.BytesIO(c.get(f"/api/chapters/{cid_m}/analysis/read/bundle").content))
    data = prompt_input(zf.read("prompt.txt").decode("utf-8"))
    raw = Script(specs(fm))(ProviderRequest("read", "m", "", json.dumps(data)))
    c.post(f"/api/chapters/{cid_m}/analysis/read/paste", json={"unit_index": 0, "raw": raw})

    def shape(cid, frames):
        d = c.get(f"/api/chapters/{cid}/dialogue").json()
        pos = {f: i for i, f in enumerate(frames)}
        return (
            d["status"],
            [(x["text"], pos[x["source_frame_id"]], pos[x["anchor_frame_id"]]) for x in d["lines"]],
            [f["frame_type"] for f in d["frames"]],
        )

    assert shape(cid_a, fa) == shape(cid_m, fm)


def test_quota_then_manual_is_not_blocked(c):
    _, cid, _ = chapter_with_frames(c)

    def quota(req):
        raise ProviderError("quota", "Hết hạn mức", "Dùng chế độ thủ công")

    use_fake(quota)
    jobs = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api"}).json()["jobs"]
    assert wait_job(c, jobs[0]["id"])["status"] == "failed"
    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "manual"})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/jobs/{jobs[1]['id']}").json()["status"] == "cancelled"
