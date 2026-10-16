import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from app import db
from app.main import create_app
from app.models.analysis import AnalysisRun, DialogueLine
from app.models.project import Asset, Chapter, Frame
from app.providers import registry
from app.providers.base import ProviderError, ProviderRequest
from app.providers.fake import FakeProvider
from app.storage import chapter_dir
from tests.analysisutil import Script, line, targets_of
from tests.apiutil import new_chapter, wait_job


@pytest.fixture
def c():
    orig = registry.factory
    with TestClient(create_app()) as client:
        yield client
    registry.factory = orig


def create_chapter_with_84_frames(c: TestClient) -> tuple[str, str, list[str], Asset]:
    pid, cid = new_chapter(c)
    cdir = chapter_dir(pid, cid)
    asset_file = cdir / "frames" / "dummy.png"
    asset_file.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    img.save(asset_file, "PNG")

    with Session(db.engine) as s:
        ch = s.get(Chapter, cid)
        assert ch
        ch.status = "frames_approved"
        s.add(ch)

        asset = Asset(
            project_id=pid,
            chapter_id=cid,
            kind="frame",
            path=f"chapters/{cid}/frames/dummy.png",
            mime_type="image/png",
            size_bytes=1000,
        )
        s.add(asset)
        s.flush()

        frame_ids = []
        for i in range(1, 85):
            fid = f"FR_{cid}_{i:03d}"
            frame_ids.append(fid)
            s.add(
                Frame(
                    id=fid,
                    chapter_id=cid,
                    idx=i,
                    asset_id=asset.id,
                    x0=0,
                    y0=(i - 1) * 10,
                    x1=100,
                    y1=i * 10,
                )
            )
        asset_id = asset.id
        s.commit()
    return pid, cid, frame_ids, asset_id


def test_quota_error_at_unit_7_and_resume_calls_only_units_7_to_14(c):
    pid, cid, frame_ids, _ = create_chapter_with_84_frames(c)

    # Frame specs
    frame_specs = {
        fid: {
            "type": "scene",
            "texts": [line(1, f"Thoại khung {fid}", speaker=None, speaker_label="nhân vật")],
        }
        for fid in frame_ids
    }
    script = Script(frame_specs)

    calls = []
    quota_error_triggered = False

    def scripted_respond(req: ProviderRequest) -> str:
        nonlocal quota_error_triggered
        calls.append(req)
        targets = targets_of(req)
        # Unit 7 is 0-indexed unit 6 (frames frame_ids[36] .. frame_ids[41])
        if frame_ids[36] in targets and not quota_error_triggered:
            quota_error_triggered = True
            raise ProviderError("quota", "Hết quota, nạp thêm credit")
        return script(req)

    fake = FakeProvider(scripted_respond)
    registry.factory = lambda: fake

    # 1. Start read analysis (read stage only, then_dialogue=False)
    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r.status_code == 200
    read_job_id = r.json()["jobs"][0]["id"]
    job_res = wait_job(c, read_job_id)
    assert job_res["status"] == "failed"
    assert "Hết quota" in (job_res.get("error_message") or "")

    # Check progress via dialogue API: 6 out of 14 units succeeded
    d_info = c.get(f"/api/chapters/{cid}/dialogue").json()
    assert d_info["read_progress"]["succeeded"] == 6
    assert d_info["read_progress"]["total"] == 14

    # 2. Re-run analysis (default: force_all=False)
    calls.clear()
    r2 = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r2.status_code == 200
    read_job_id_2 = r2.json()["jobs"][0]["id"]
    job_res_2 = wait_job(c, read_job_id_2)
    assert job_res_2["status"] == "succeeded"

    # Provider should ONLY be called for units 7–14 (unit index 6–13) => exactly 8 calls
    assert len(calls) == 8
    target_sets = [targets_of(req) for req in calls]
    assert target_sets[0] == frame_ids[36:42]  # Unit 7 (0-indexed 6)
    assert target_sets[-1] == frame_ids[78:84]  # Unit 14 (0-indexed 13)

    # Job logs must record skipping already succeeded units 1..6
    job_logs = c.get(f"/api/jobs/{read_job_id_2}/log").text
    assert "phần 1: đã có kết quả, bỏ qua" in job_logs
    assert "phần 6: đã có kết quả, bỏ qua" in job_logs

    d_info_2 = c.get(f"/api/chapters/{cid}/dialogue").json()
    assert d_info_2["read_progress"]["succeeded"] == 14
    assert d_info_2["read_progress"]["total"] == 14


def test_edit_frame_in_package_3_reruns_only_package_3(c):
    pid, cid, frame_ids, asset_id = create_chapter_with_84_frames(c)

    frame_specs = {
        fid: {
            "type": "scene",
            "texts": [line(1, f"Thoại khung {fid}", speaker=None, speaker_label="nhân vật")],
        }
        for fid in frame_ids
    }
    script = Script(frame_specs)

    calls = []

    def scripted_respond(req: ProviderRequest) -> str:
        calls.append(req)
        return script(req)

    fake = FakeProvider(scripted_respond)
    registry.factory = lambda: fake

    # Run initial analysis for all 14 units
    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r.status_code == 200
    wait_job(c, r.json()["jobs"][0]["id"])
    assert len(calls) == 14

    # Edit frame 15 (which belongs to package 3: frames 13..18)
    new_frame_15_id = f"FR_{cid}_015_new"
    with Session(db.engine) as s:
        for d in s.exec(select(DialogueLine).where(DialogueLine.source_frame_id == frame_ids[14])):
            s.delete(d)
        for d in s.exec(select(DialogueLine).where(DialogueLine.anchor_frame_id == frame_ids[14])):
            d.anchor_frame_id = None
            s.add(d)
        s.flush()
        old_f15 = s.get(Frame, frame_ids[14])
        assert old_f15
        s.delete(old_f15)
        s.add(
            Frame(
                id=new_frame_15_id,
                chapter_id=cid,
                idx=15,
                asset_id=asset_id,
                x0=0,
                y0=140,
                x1=100,
                y1=150,
            )
        )
        s.commit()

    # Re-run read analysis
    calls.clear()
    r2 = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r2.status_code == 200
    read_job_2 = r2.json()["jobs"][0]["id"]
    wait_job(c, read_job_2)

    # Provider should ONLY be called for package 3 (unit index 2) => exactly 1 call!
    assert len(calls) == 1
    call_targets = targets_of(calls[0])
    assert new_frame_15_id in call_targets
    assert call_targets == [
        frame_ids[12],
        frame_ids[13],
        new_frame_15_id,
        frame_ids[15],
        frame_ids[16],
        frame_ids[17],
    ]

    job_logs = c.get(f"/api/jobs/{read_job_2}/log").text
    assert "phần 1: đã có kết quả, bỏ qua" in job_logs
    assert "phần 2: đã có kết quả, bỏ qua" in job_logs
    assert "phần 4: đã có kết quả, bỏ qua" in job_logs
    assert "phần 14: đã có kết quả, bỏ qua" in job_logs


def test_frame_removal_does_not_rerun_packages(c):
    pid, cid, frame_ids, _ = create_chapter_with_84_frames(c)

    frame_specs = {
        fid: {
            "type": "scene",
            "texts": [line(1, f"Thoại khung {fid}", speaker=None, speaker_label="nhân vật")],
        }
        for fid in frame_ids
    }
    script = Script(frame_specs)

    calls = []

    def scripted_respond(req: ProviderRequest) -> str:
        calls.append(req)
        return script(req)

    fake = FakeProvider(scripted_respond)
    registry.factory = lambda: fake

    # Run initial analysis
    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r.status_code == 200
    wait_job(c, r.json()["jobs"][0]["id"])
    assert len(calls) == 14

    # Remove frame 2 (index 1) in package 1
    removed_fid = frame_ids[1]
    with Session(db.engine) as s:
        for d in s.exec(select(DialogueLine).where(DialogueLine.source_frame_id == removed_fid)):
            s.delete(d)
        for d in s.exec(select(DialogueLine).where(DialogueLine.anchor_frame_id == removed_fid)):
            d.anchor_frame_id = None
            s.add(d)
        s.flush()
        f2 = s.get(Frame, removed_fid)
        assert f2
        s.delete(f2)
        for r_run in s.exec(
            select(AnalysisRun).where(AnalysisRun.chapter_id == cid, AnalysisRun.stage == "read")
        ):
            cur_targets = (r_run.payload or {}).get("targets", [])
            new_targets = [fid for fid in cur_targets if fid != removed_fid]
            if len(new_targets) != len(cur_targets):
                r_run.payload = {**(r_run.payload or {}), "targets": new_targets}
                s.add(r_run)
        s.commit()

    # Re-run read analysis
    calls.clear()
    r2 = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r2.status_code == 200
    wait_job(c, r2.json()["jobs"][0]["id"])

    # Provider should NOT be called for any package (0 calls)
    assert len(calls) == 0


def test_payload_output_reapplies_without_ai_when_lines_undone(c):
    pid, cid, frame_ids, _ = create_chapter_with_84_frames(c)

    frame_specs = {
        fid: {
            "type": "scene",
            "texts": [line(1, f"Thoại khung {fid}", speaker=None, speaker_label="nhân vật")],
        }
        for fid in frame_ids
    }
    script = Script(frame_specs)

    calls = []

    def scripted_respond(req: ProviderRequest) -> str:
        calls.append(req)
        return script(req)

    fake = FakeProvider(scripted_respond)
    registry.factory = lambda: fake

    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r.status_code == 200
    wait_job(c, r.json()["jobs"][0]["id"])
    assert len(calls) == 14

    # Check AnalysisRun payload contains "output"
    with Session(db.engine) as s:
        run0 = s.exec(
            select(AnalysisRun).where(
                AnalysisRun.chapter_id == cid,
                AnalysisRun.stage == "read",
                AnalysisRun.unit_index == 0,
            )
        ).first()
        assert run0 is not None
        assert "output" in (run0.payload or {})
        assert len(run0.payload["output"]["frames"]) == 6

        # Simulate frame lines missing / undone
        unit0_targets = run0.payload["targets"]
        lines = s.exec(
            select(DialogueLine).where(
                DialogueLine.chapter_id == cid, DialogueLine.source_frame_id.in_(unit0_targets)
            )
        ).all()
        assert len(lines) > 0
        for d in lines:
            s.delete(d)
        s.commit()

    # Re-run analysis
    calls.clear()
    r2 = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r2.status_code == 200
    wait_job(c, r2.json()["jobs"][0]["id"])

    # Provider was NOT called (0 calls)
    assert len(calls) == 0

    # Dialogue lines for unit 0 were restored from payload["output"]
    with Session(db.engine) as s:
        restored = s.exec(
            select(DialogueLine).where(
                DialogueLine.chapter_id == cid, DialogueLine.source_frame_id.in_(unit0_targets)
            )
        ).all()
        assert len(restored) > 0


def test_force_all_reruns_all_packages(c):
    pid, cid, frame_ids, _ = create_chapter_with_84_frames(c)

    frame_specs = {
        fid: {
            "type": "scene",
            "texts": [line(1, f"Thoại khung {fid}", speaker=None, speaker_label="nhân vật")],
        }
        for fid in frame_ids
    }
    script = Script(frame_specs)

    calls = []

    def scripted_respond(req: ProviderRequest) -> str:
        calls.append(req)
        return script(req)

    fake = FakeProvider(scripted_respond)
    registry.factory = lambda: fake

    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r.status_code == 200
    wait_job(c, r.json()["jobs"][0]["id"])
    assert len(calls) == 14

    # Now call with force_all=True
    calls.clear()
    r2 = c.post(
        f"/api/chapters/{cid}/analysis/read",
        json={"mode": "api", "then_dialogue": False, "force_all": True},
    )
    assert r2.status_code == 200
    wait_job(c, r2.json()["jobs"][0]["id"])

    # All 14 packages were re-run
    assert len(calls) == 14


def test_dialogue_incremental_and_repolish_all(c):
    pid, cid, frame_ids, _ = create_chapter_with_84_frames(c)

    frame_specs = {
        fid: {
            "type": "scene",
            "texts": [line(1, f"Thoại khung {fid}", speaker=None, speaker_label="nhân vật")],
        }
        for fid in frame_ids
    }
    script = Script(frame_specs, polish=lambda t: f"{t} (đã sửa)")

    calls = []

    def scripted_respond(req: ProviderRequest) -> str:
        calls.append(req)
        return script(req)

    fake = FakeProvider(scripted_respond)
    registry.factory = lambda: fake

    # 1. Read
    r = c.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False})
    assert r.status_code == 200
    wait_job(c, r.json()["jobs"][0]["id"])

    # 2. Dialogue polish initial run
    calls.clear()
    r_diag = c.post(f"/api/chapters/{cid}/analysis/dialogue", json={"mode": "api"})
    assert r_diag.status_code == 200
    wait_job(c, r_diag.json()["jobs"][0]["id"])
    assert len(calls) > 0
    first_run_calls = len(calls)

    # 3. Dialogue polish again with force_all=False
    # All lines are already polished, so 0 calls
    calls.clear()
    r_diag2 = c.post(
        f"/api/chapters/{cid}/analysis/dialogue", json={"mode": "api", "force_all": False}
    )
    assert r_diag2.status_code == 200
    wait_job(c, r_diag2.json()["jobs"][0]["id"])
    assert len(calls) == 0

    # 4. Dialogue polish with force_all=True
    # All lines re-polished
    calls.clear()
    r_diag3 = c.post(
        f"/api/chapters/{cid}/analysis/dialogue", json={"mode": "api", "force_all": True}
    )
    assert r_diag3.status_code == 200
    wait_job(c, r_diag3.json()["jobs"][0]["id"])
    assert len(calls) == first_run_calls
