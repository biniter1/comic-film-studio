import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import registry
from app.providers.base import ProviderError
from tests.analysisutil import Script, chapter_with_frames, line, use_fake
from tests.apiutil import wait_job


@pytest.fixture
def c():
    orig = registry.factory
    with TestClient(create_app()) as client:
        yield client
    registry.factory = orig


def run_api(c, cid):
    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api"})
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    return [wait_job(c, j["id"]) for j in jobs]


def standard_script(frames, **kw):
    f1, f2, f3 = frames
    return Script(
        {
            f1: {
                "texts": [
                    line(
                        1,
                        "Lam Phong, ngươi tới rồi.",
                        speaker=None,
                        speaker_label="lão giả",
                        conf=0.4,
                    )
                ]
            },
            f2: {
                "type": "dialogue_only",
                "texts": [line(1, "Ta tới lấy mạng ngươi!", belongs_to="prev")],
            },
            f3: {"texts": [line(1, "ẦM", speaker=None, kind="sfx")]},
        },
        **kw,
    )


def test_requires_approved_frames(c):
    _, cid, _ = chapter_with_frames(c, approve=False)
    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "FRAMES_NOT_APPROVED"


def test_full_api_flow_anchor_polish_glossary(c):
    pid, cid, frames = chapter_with_frames(c)
    c.post(
        f"/api/projects/{pid}/glossary",
        json={"term": "Lâm Phong", "kind": "person", "variants": ["Lam Phong"]},
    )
    use_fake(
        standard_script(
            frames,
            polish=lambda t: t.replace("ngươi tới rồi", "cuối cùng ngươi cũng tới"),
            glossary=[
                {"term": "Huyết Ma Công", "kind": "technique", "variants": ["huyet ma cong"]}
            ],
        )
    )
    jobs = run_api(c, cid)
    assert [j["status"] for j in jobs] == ["succeeded", "succeeded"], jobs

    d = c.get(f"/api/chapters/{cid}/dialogue").json()
    assert d["status"] == "dialogue_draft"
    types = {f["id"]: f["frame_type"] for f in d["frames"]}
    assert types[frames[1]] == "dialogue_only"
    lines = d["lines"]
    assert [x["order"] for x in lines] == [1, 2, 3]
    l1, l2, l3 = lines
    # dialogue_only frame's line is shown with the previous scene
    assert l2["source_frame_id"] == frames[1] and l2["anchor_frame_id"] == frames[0]
    # polish + deterministic glossary
    assert l1["text"] == "Lâm Phong, cuối cùng ngươi cũng tới."
    assert l1["text_raw"] == "Lam Phong, ngươi tới rồi." and l1["edited_by"] == "ai"
    assert l1["needs_review"]  # speaker confidence 0.4
    assert l3["kind"] == "sfx" and l3["text"] == "ẦM"
    assert any(ch["key"] == "lam_phong" for ch in d["characters"])
    gl = c.get(f"/api/projects/{pid}/glossary").json()
    assert any(t["term"] == "Huyết Ma Công" and t["status"] == "suggested" for t in gl)

    # approval gated by review
    r = c.post(f"/api/chapters/{cid}/dialogue/approve")
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_PENDING"
    assert c.post(f"/api/chapters/{cid}/dialogue/review-all").json()["reviewed"] == 1
    assert c.post(f"/api/chapters/{cid}/dialogue/approve").json()["status"] == "dialogue_approved"


def test_user_edit_survives_rerun_and_edit_reopens_draft(c):
    pid, cid, frames = chapter_with_frames(c)
    script = standard_script(frames, polish=lambda t: t + " (AI)")
    fake = use_fake(script)
    run_api(c, cid)
    lines = c.get(f"/api/chapters/{cid}/dialogue").json()["lines"]
    c.post(f"/api/chapters/{cid}/dialogue/review-all")
    c.post(f"/api/chapters/{cid}/dialogue/approve")

    r = c.patch(f"/api/dialogue/{lines[1]['id']}", json={"text": "Ta đến đòi mạng ngươi!"})
    assert r.status_code == 200 and r.json()["edited_by"] == "user"
    assert c.get(f"/api/chapters/{cid}").json()["status"] == "dialogue_draft"

    n_calls = len(fake.calls)
    script.polish = lambda t: t + " (AI v2)"
    r = c.post(f"/api/chapters/{cid}/analysis/dialogue", json={"mode": "api", "force_all": True})
    assert wait_job(c, r.json()["jobs"][0]["id"])["status"] == "succeeded"
    # the user line was not even sent as a target
    sent = json.loads(fake.calls[n_calls].user_text)
    assert lines[1]["id"] not in [x["line_id"] for x in sent["TARGET_LINES"]]
    assert "Ta đến đòi mạng ngươi!" in [x["text"] for x in sent["LOCKED_LINES"]]
    after = {x["id"]: x for x in c.get(f"/api/chapters/{cid}/dialogue").json()["lines"]}
    assert after[lines[1]["id"]]["text"] == "Ta đến đòi mạng ngươi!"
    assert after[lines[0]["id"]]["text"].endswith("(AI v2)")

    # revert
    r = c.post(f"/api/dialogue/{lines[1]['id']}/revert").json()
    assert r["text"] == r["text_raw"] and r["edited_by"] == "none"


def test_change_speaker_frame_type_and_anchor(c):
    pid, cid, frames = chapter_with_frames(c)
    use_fake(standard_script(frames))
    run_api(c, cid)
    lines = c.get(f"/api/chapters/{cid}/dialogue").json()["lines"]
    ch = c.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Huyết Lão", "gender": "male", "age_group": "elderly"},
    ).json()
    r = c.patch(f"/api/dialogue/{lines[0]['id']}", json={"speaker_key": ch["key"]}).json()
    assert r["speaker_key"] == "huyet_lao" and r["speaker_age"] == "elderly"
    assert r["speaker_confidence"] == 1.0 and r["reviewed"]
    assert (
        c.patch(f"/api/dialogue/{lines[0]['id']}", json={"speaker_key": "nobody"}).status_code
        == 422
    )

    # user marks frame 2 as a scene → its line anchors to itself
    c.patch(f"/api/frames/{frames[1]}", json={"frame_type": "scene"})
    l2 = c.get(f"/api/chapters/{cid}/dialogue").json()["lines"][1]
    assert l2["anchor_frame_id"] == frames[1]
    # manual anchor is locked
    c.patch(f"/api/dialogue/{l2['id']}", json={"anchor_frame_id": frames[2]})
    c.patch(f"/api/frames/{frames[1]}", json={"frame_type": "dialogue_only"})
    l2 = c.get(f"/api/chapters/{cid}/dialogue").json()["lines"][1]
    assert l2["anchor_frame_id"] == frames[2] and l2["anchor_locked"]


def test_quota_error_fails_job_with_user_action(c):
    _, cid, _ = chapter_with_frames(c)

    def quota(req):
        raise ProviderError("quota", "Hết hạn mức", "Dùng chế độ thủ công")

    use_fake(quota)
    jobs = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api"}).json()["jobs"]
    read = wait_job(c, jobs[0]["id"])
    assert read["status"] == "failed" and read["error_category"] == "quota"
    assert "thủ công" in read["user_action_required"]


def test_frame_changes_vs_script(c):
    _, cid, frames = chapter_with_frames(c)
    use_fake(standard_script(frames))
    run_api(c, cid)
    fr = c.get(f"/api/chapters/{cid}/frames").json()["frames"]
    ranges = [{"y0": f["y0"], "y1": f["y1"]} for f in fr]

    def put(rs):
        r = c.put(f"/api/chapters/{cid}/frames", json={"frames": rs})
        assert r.status_code == 200, r.text
        return c.get(f"/api/chapters/{cid}/dialogue").json()

    # unchanged save keeps the script
    d = put(ranges)
    assert d["status"] == "dialogue_draft" and len(d["lines"]) == 3
    # removing frame 1 (e.g. a banner) keeps the rest; frame 2's line re-anchors to frame 3
    d = put(ranges[1:])
    assert d["status"] == "dialogue_draft"
    assert [x["source_frame_id"] for x in d["lines"]] == frames[1:]
    assert d["lines"][0]["anchor_frame_id"] == frames[2]
    assert [x["order"] for x in d["lines"]] == [1, 2]
    # a changed range removes only the affected frame's lines; unaffected frames and status survive
    changed = [dict(ranges[1], y1=ranges[1]["y1"] - 10), ranges[2]]
    d = put(changed)
    assert d["status"] == "dialogue_draft"
    assert [x["source_frame_id"] for x in d["lines"]] == [frames[2]]


def test_glossary_merge_and_character_merge(c):
    pid, cid, frames = chapter_with_frames(c)
    a = c.post(f"/api/projects/{pid}/glossary", json={"term": "Lâm Phong", "variants": []}).json()
    b = c.post(f"/api/projects/{pid}/glossary", json={"term": "Lam Phong"}).json()
    assert c.post(f"/api/projects/{pid}/glossary", json={"term": "lâm phong"}).status_code == 409
    m = c.post(f"/api/glossary/{b['id']}/merge", json={"into_id": a["id"]}).json()
    assert m["variants"] == ["Lam Phong"]
    assert len(c.get(f"/api/projects/{pid}/glossary").json()) == 1

    use_fake(standard_script(frames))
    run_api(c, cid)
    dup = c.post(f"/api/projects/{pid}/characters", json={"name": "Phong ca"}).json()
    lines = c.get(f"/api/chapters/{cid}/dialogue").json()["lines"]
    c.patch(f"/api/dialogue/{lines[1]['id']}", json={"speaker_key": dup["key"]})
    main = next(
        x for x in c.get(f"/api/projects/{pid}/characters").json() if x["key"] == "lam_phong"
    )
    merged = c.post(f"/api/characters/{dup['id']}/merge", json={"into_id": main["id"]}).json()
    assert "Phong ca" in merged["aliases"]
    l2 = c.get(f"/api/chapters/{cid}/dialogue").json()["lines"][1]
    assert l2["speaker_key"] == "lam_phong"
