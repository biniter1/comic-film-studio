import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.providers import registry
from tests.analysisutil import Script, chapter_with_frames, line, use_fake
from tests.apiutil import wait_job


@pytest.fixture
def c():
    orig = registry.factory
    with TestClient(create_app()) as client:
        yield client
    registry.factory = orig


class Director:
    """Fake provider for all 4 stages."""

    def __init__(self, frames):
        self.read = Script(
            {
                frames[0]: {"texts": [line(1, "Ngươi là ai?")]},
                frames[1]: {"texts": [line(1, "Huyết Ma Chưởng!", kind="technique_name")]},
                frames[2]: {"texts": [line(1, "Ta là ta.")]},
            }
        )
        self.calls = {"plan": 0, "shots": 0}

    def __call__(self, req):
        if req.stage in ("read", "dialogue"):
            return self.read(req)
        data = json.loads(req.user_text)
        self.calls[req.stage] += 1
        if req.stage == "plan":
            ids = [f["frame_id"] for f in data["SCENE_FRAMES"]]
            return json.dumps(
                {
                    "scenes": [
                        {"frame_ids": ids[:2], "summary": "duel", "location_key": "hall"},
                        {"frame_ids": ids[2:], "summary": "after", "location_key": "hall"},
                    ],
                    "new_locations": [
                        {"key": "hall", "name_vi": "Đại điện", "location_lock": "stone hall"}
                    ],
                }
            )
        shots = []
        for i, f in enumerate(data["FRAMES"]):
            shots.append(
                {
                    "frame_ids": [f["frame_id"]],
                    "transition_in": "continuous" if i else "cut",
                    "duration_s": 4,
                    "camera": {"shot_size": "CU", "movement": "dolly in", "speed": "normal"},
                    "blocking": [
                        {
                            "character_key": "lam_phong",
                            "screen_pos": "Left",
                            "depth": "foreground",
                            "facing": "right",
                            "pose": "fist raised",
                        }
                    ],
                    "beats": [
                        {"t0": 0, "t1": 2, "action": "he clenches his fist"},
                        {"t0": 2, "t1": 4, "action": "red aura flares"},
                    ],
                    "start_state": "fist raised",
                    "end_state": "aura fills the frame",
                    "line_ids": [],
                }
            )
        return json.dumps({"shots": shots})


def approved_dialogue(c):
    pid, cid, frames = chapter_with_frames(c)
    d = Director(frames)
    use_fake(d)
    jobs = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api"}).json()["jobs"]
    assert [wait_job(c, j["id"])["status"] for j in jobs] == ["succeeded", "succeeded"]
    c.post(f"/api/chapters/{cid}/dialogue/review-all")
    assert c.post(f"/api/chapters/{cid}/dialogue/approve").status_code == 200
    return pid, cid, frames, d


def test_plan_requires_approved_dialogue(c):
    _, cid, _ = chapter_with_frames(c)
    r = c.post(f"/api/chapters/{cid}/analysis/plan", json={"mode": "api"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "DIALOGUE_NOT_APPROVED"


def test_plan_and_shots_end_to_end(c):
    pid, cid, frames, d = approved_dialogue(c)
    jobs = c.post(f"/api/chapters/{cid}/analysis/plan", json={"mode": "api"}).json()["jobs"]
    assert [wait_job(c, j["id"])["status"] for j in jobs] == ["succeeded", "succeeded"], jobs
    data = c.get(f"/api/chapters/{cid}/shots").json()
    assert data["status"] == "shots_draft"
    assert [s["code"] for s in data["scenes"]] == ["SC01", "SC02"]
    shots = data["shots"]
    assert [s["code"] for s in shots] == ["SH001", "SH002", "SH003"]
    # loose enums normalised, chains: SH002 continuous in scene 1, SH003 starts scene 2 → cut
    assert shots[0]["camera"] == {
        "shot_size": "close_up",
        "movement": "push_in",
        "speed": "medium",
        "angle": "eye",
    }
    assert shots[0]["blocking"][0]["screen_pos"] == "left"
    assert [(s["chain_code"], s["transition_in"]) for s in shots] == [
        ("C01", "cut"),
        ("C01", "continuous"),
        ("C02", "cut"),
    ]
    # lines assigned by code (fake returned none), technique → title
    assert [ln["text"] for ln in shots[0]["lines"]] == ["Ngươi là ai?"]
    assert shots[1]["titles"][0]["style"] == "technique"
    # prompts composed in code
    assert shots[0]["video_prompt"].startswith("Push in, medium, close-up.")
    assert "Image 1 is the comic panel" in shots[0]["keyframe_prompt"]
    assert shots[0]["attachments"][0]["kind"] == "frame"
    assert any(loc["key"] == "hall" for loc in data["locations"])

    # edit a shot → recomposed; override prompt sticks
    sid = shots[0]["id"]
    r = c.patch(f"/api/shots/{sid}", json={"camera": {"movement": "orbit"}})
    assert r.status_code == 200 and r.json()["video_prompt"].startswith("Orbit right")
    r = c.patch(f"/api/shots/{sid}", json={"prompt_override": {"video": "My own prompt"}})
    assert r.json()["video_prompt"] == "My own prompt" and r.json()["edited_by"] == "user"
    assert (
        c.patch(f"/api/shots/{sid}", json={"camera": {"movement": "teleport"}}).status_code == 422
    )

    assert c.post(f"/api/chapters/{cid}/shots/approve-plan").json()["status"] == "plan_approved"

    # running again costs nothing: plan + shots units are skipped
    calls = dict(d.calls)
    jobs = c.post(f"/api/chapters/{cid}/analysis/plan", json={"mode": "api"}).json()["jobs"]
    assert [wait_job(c, j["id"])["status"] for j in jobs] == ["succeeded", "succeeded"]
    assert d.calls == calls


def test_removing_a_frame_strips_it_from_shots(c):
    pid, cid, frames, d = approved_dialogue(c)
    jobs = c.post(f"/api/chapters/{cid}/analysis/plan", json={"mode": "api"}).json()["jobs"]
    [wait_job(c, j["id"]) for j in jobs]
    fr = c.get(f"/api/chapters/{cid}/frames").json()["frames"]
    c.put(
        f"/api/chapters/{cid}/frames",
        json={"frames": [{"y0": f["y0"], "y1": f["y1"]} for f in fr[:2]]},
    )
    shots = c.get(f"/api/chapters/{cid}/shots").json()["shots"]
    assert all(frames[2] not in s["frame_ids"] for s in shots)


def test_manual_mode_for_shots(c):
    pid, cid, frames, d = approved_dialogue(c)
    r = c.post(f"/api/chapters/{cid}/analysis/plan", json={"mode": "manual"})
    assert r.status_code == 200 and len(r.json()["units"]) == 1
