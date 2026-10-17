"""Tests for Phase 2b1: Character refs (crop & upload), AI Look Profile,
Character roles (main/supporting/extra) and crowd groups (SPEC §4.6, §5.2)."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session

from app import db
from app.analysis import stages
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


def _png_bytes(w: int = 400, h: int = 300, color: tuple[int, int, int] = (100, 150, 200)) -> bytes:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Crop character ref: valid & bounds validation -> 422
# ---------------------------------------------------------------------------
def test_crop_character_ref_valid_and_bounds_validation(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=2)
    fid = frames[0]

    c = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Lâm Phong", "gender": "male", "age_group": "young_adult"},
    ).json()
    chid = c["id"]

    # 1. Valid crop (e.g. 100x100 within 400x300) -> 201
    r_valid = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": fid, "x0": 10, "y0": 10, "x1": 110, "y1": 110, "note": "face close-up"},
    )
    assert r_valid.status_code == 201
    ref_data = r_valid.json()
    assert ref_data["id"].startswith("RF")
    assert ref_data["order"] == 1
    assert ref_data["crop"] == {"x0": 10, "y0": 10, "x1": 110, "y1": 110}
    assert ref_data["source_frame_id"] == fid
    assert ref_data["note"] == "face close-up"
    assert "/api/assets/" in ref_data["image_url"]

    # 2. Out of bounds: x1 > frame width (600) -> 422
    r_oob_x = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": fid, "x0": 10, "y0": 10, "x1": 700, "y1": 110},
    )
    assert r_oob_x.status_code == 422
    assert r_oob_x.json()["error"]["code"] == "INVALID_CROP"

    # Out of bounds: y1 > frame height -> 422
    r_oob_y = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": fid, "x0": 10, "y0": 10, "x1": 100, "y1": 1000},
    )
    assert r_oob_y.status_code == 422

    # Negative coordinates -> 422
    r_neg = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": fid, "x0": -5, "y0": 10, "x1": 100, "y1": 110},
    )
    assert r_neg.status_code == 422

    # Inverted coordinates: x0 >= x1 -> 422
    r_inv = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": fid, "x0": 100, "y0": 10, "x1": 50, "y1": 110},
    )
    assert r_inv.status_code == 422

    # 3. Too small: cw < 64 or ch < 64 -> 422
    r_small = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": fid, "x0": 10, "y0": 10, "x1": 60, "y1": 60},  # 50x50 < 64x64
    )
    assert r_small.status_code == 422
    assert r_small.json()["error"]["code"] == "INVALID_CROP"


# ---------------------------------------------------------------------------
# 2. Upload character ref: corrupt image -> 422 & valid upload
# ---------------------------------------------------------------------------
def test_upload_character_ref_corrupt_and_valid(client: TestClient):
    p = client.post("/api/projects", json={"name": "Dự án Upload Ref"}).json()
    pid = p["id"]

    c = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Tiêu Viêm", "gender": "male", "age_group": "teen"},
    ).json()
    chid = c["id"]

    # 1. Corrupt image bytes -> 422
    r_corrupt = client.post(
        f"/api/characters/{chid}/refs/upload",
        files={"file": ("corrupt.jpg", b"not-a-valid-image-bytes", "image/jpeg")},
    )
    assert r_corrupt.status_code == 422
    assert r_corrupt.json()["error"]["code"] == "INVALID_IMAGE"

    # 2. Valid image -> 201
    valid_bytes = _png_bytes(200, 200)
    r_valid = client.post(
        f"/api/characters/{chid}/refs/upload",
        files={"file": ("ref.png", valid_bytes, "image/png")},
        data={"note": "uploaded reference"},
    )
    assert r_valid.status_code == 201
    ref = r_valid.json()
    rid = ref["id"]
    assert ref["order"] == 1
    assert ref["note"] == "uploaded reference"
    assert ref["crop"] is None
    assert ref["source_frame_id"] is None

    # List refs
    refs_list = client.get(f"/api/characters/{chid}/refs").json()
    assert len(refs_list) == 1
    assert refs_list[0]["id"] == rid

    # Patch ref
    patch_res = client.patch(f"/api/refs/{rid}", json={"order": 5, "note": "updated note"})
    assert patch_res.status_code == 200
    assert patch_res.json()["order"] == 5
    assert patch_res.json()["note"] == "updated note"

    # Delete ref
    del_res = client.delete(f"/api/refs/{rid}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] == rid
    assert len(client.get(f"/api/characters/{chid}/refs").json()) == 0


# ---------------------------------------------------------------------------
# 3. Sheet bundle uses char_ref instead of frames (prioritizing outfit)
# ---------------------------------------------------------------------------
def test_sheet_bundle_uses_char_ref_prioritizing_outfit(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=2)

    # Character A: normal character
    c = client.post(
        f"/api/projects/{pid}/characters",
        json={
            "name": "Hàn Lập",
            "look_lock": "plain looking youth, dark skin",
        },
    ).json()
    chid = c["id"]
    outfits = client.get(f"/api/characters/{chid}/outfits").json()
    default_oid = outfits[0]["id"]

    # Character B: group character -> NO sheet allowed
    group_c = client.post(
        f"/api/projects/{pid}/characters",
        json={
            "name": "Nhóm Đệ Tử",
            "is_group": True,
            "group_size_hint": "3-5 người",
            "role": "extra",
        },
    ).json()
    group_outfits = client.get(f"/api/characters/{group_c['id']}/outfits").json()
    group_oid = group_outfits[0]["id"]

    # Group character sheet bundle blocked -> 400 GROUP_HAS_NO_SHEET
    b_group = client.get(f"/api/outfits/{group_oid}/sheet-bundle")
    assert b_group.status_code == 400
    assert b_group.json()["error"]["code"] == "GROUP_HAS_NO_SHEET"

    # Group character sheet upload blocked -> 400 GROUP_HAS_NO_SHEET
    up_group = client.post(
        f"/api/outfits/{group_oid}/sheet",
        files={"file": ("sheet.png", _png_bytes(200, 200), "image/png")},
    )
    assert up_group.status_code == 400
    assert up_group.json()["error"]["code"] == "GROUP_HAS_NO_SHEET"

    # For normal character: empty refs -> 409
    b_empty = client.get(f"/api/outfits/{default_oid}/sheet-bundle")
    assert b_empty.status_code == 409
    assert b_empty.json()["error"]["code"] == "REF_IMAGES_REQUIRED"

    # Add second outfit for Hàn Lập
    o2 = client.post(
        f"/api/characters/{chid}/outfits",
        json={"name_vi": "Hoàng Bào", "outfit_lock": "yellow daoist robe", "is_default": False},
    ).json()
    o2_id = o2["id"]

    # Crop ref 1: general (no outfit_id)
    r_gen = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": frames[0], "x0": 0, "y0": 0, "x1": 100, "y1": 100},
    ).json()

    # Crop ref 2: attached specifically to outfit o2
    r_o2 = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": frames[1], "x0": 50, "y0": 50, "x1": 150, "y1": 150, "outfit_id": o2_id},
    ).json()

    # Download sheet bundle for outfit o2:
    # Outfit-specific ref (r_o2) must be prioritized first (01_...), general ref second (02_...)
    b_o2 = client.get(f"/api/outfits/{o2_id}/sheet-bundle")
    assert b_o2.status_code == 200
    assert b_o2.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(b_o2.content)) as zf:
        namelist = zf.namelist()
        assert "prompt.txt" in namelist
        assert f"01_{r_o2['id']}.jpg" in namelist
        assert f"02_{r_gen['id']}.jpg" in namelist


# ---------------------------------------------------------------------------
# 4. Look-profile with fake provider -> proposal saved, not overwritten until applied
# ---------------------------------------------------------------------------
def test_look_profile_with_fake_provider_and_proposal(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=1)

    c = client.post(
        f"/api/projects/{pid}/characters",
        json={
            "name": "Bạch Tiểu Thuần",
            "look_lock": "initial look lock text",
            "height_class": "average",
        },
    ).json()
    chid = c["id"]

    # Must have at least 1 ref to run look-profile
    no_ref = client.post(f"/api/characters/{chid}/look-profile")
    assert no_ref.status_code == 400
    assert no_ref.json()["error"]["code"] == "NO_REF_IMAGES"

    # Add 1 ref
    r = client.post(
        f"/api/characters/{chid}/refs/crop",
        json={"frame_id": frames[0], "x0": 10, "y0": 10, "x1": 100, "y1": 100},
    ).json()
    assert r["id"]

    # Script fake provider for character_profile stage
    proposed_profile = {
        "look_lock": "slender fair-skinned youth, delicate phoenix eyes, dark hair in topknot",
        "outfit_lock": "light green outer robe with silver clouds, wooden hairpin",
        "short_id": "light green robe",
        "height_class": "short",
        "palette": ["light green", "silver", "white"],
        "distinctive": ["phoenix eyes", "wooden hairpin"],
    }

    def respond(req):
        if req.stage == "character_profile":
            return json.dumps(proposed_profile, ensure_ascii=False)
        raise ValueError(f"unexpected stage: {req.stage}")

    registry.factory = lambda: FakeProvider(respond)

    # Enqueue look profile
    res = client.post(f"/api/characters/{chid}/look-profile")
    assert res.status_code == 200
    job_id = res.json()["job_id"]

    wait_job(client, job_id)

    # Character proposal is populated, but current fields are NOT overwritten
    bible = client.get(f"/api/projects/{pid}/bible").json()
    char_in_bible = next(x for x in bible["characters"] if x["id"] == chid)
    assert char_in_bible["look_lock"] == "initial look lock text"
    assert char_in_bible["height_class"] == "average"
    assert char_in_bible["profile_proposal"] is not None
    assert char_in_bible["profile_proposal"]["look_lock"] == proposed_profile["look_lock"]

    # Apply only look_lock field
    apply_one = client.post(
        f"/api/characters/{chid}/apply-proposal",
        json={"fields": ["look_lock"]},
    )
    assert apply_one.status_code == 200
    c_updated = apply_one.json()
    assert c_updated["look_lock"] == proposed_profile["look_lock"]
    assert c_updated["height_class"] == "average"  # still unchanged

    # Apply all fields
    apply_all = client.post(
        f"/api/characters/{chid}/apply-proposal",
        json={"fields": None},
    )
    assert apply_all.status_code == 200
    c_all = apply_all.json()
    assert c_all["height_class"] == "short"

    outfits = client.get(f"/api/characters/{chid}/outfits").json()
    def_outfit = outfits[0]
    assert def_outfit["outfit_lock"] == proposed_profile["outfit_lock"]
    assert def_outfit["short_id"] == proposed_profile["short_id"]


# ---------------------------------------------------------------------------
# 5. Read stage: groups crowd characters into 1 is_group=True character
# ---------------------------------------------------------------------------
def test_read_stage_groups_similar_disciples(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=2)

    # Script fake provider for read
    read_output = {
        "frames": [
            {
                "frame_id": frames[0],
                "frame_type": "scene",
                "description": "Hai đệ tử đứng gác trước cổng",
                "characters": ["nhom_de_tu_gac_cong"],
                "texts": [
                    {
                        "line_no": 1,
                        "kind": "dialogue",
                        "text": "Đứng lại! Ai cho các ngươi vào?",
                        "speaker_key": "nhom_de_tu_gac_cong",
                        "speaker_label": "đệ tử",
                        "speaker_gender": "male",
                        "speaker_age": "young_adult",
                        "speaker_confidence": 0.9,
                        "belongs_to": "self",
                    }
                ],
            },
            {
                "frame_id": frames[1],
                "frame_type": "scene",
                "description": "Hai đệ tử rút kiếm",
                "characters": ["nhom_de_tu_gac_cong"],
                "texts": [],
            },
        ],
        "new_characters": [
            {
                "key": "nhom_de_tu_gac_cong",
                "name": "Nhóm Đệ Tử Gác Cổng",
                "gender": "male",
                "age_group": "young_adult",
                "role": "extra",
                "is_group": True,
                "group_size_hint": "2 người",
            }
        ],
        "running_summary": "Hai đệ tử gác cổng chặn đường",
    }

    def respond(req):
        if req.stage == "read":
            return json.dumps(read_output, ensure_ascii=False)
        raise ValueError(f"unexpected stage: {req.stage}")

    registry.factory = lambda: FakeProvider(respond)

    # Run read stage
    res = client.post(
        f"/api/chapters/{cid}/analysis/read", json={"mode": "api", "then_dialogue": False}
    )
    assert res.status_code == 200
    jobs = res.json()["jobs"]
    for j in jobs:
        wait_job(client, j["id"])

    # Check character in project
    chars = client.get(f"/api/projects/{pid}/characters").json()
    group_char = next((ch for ch in chars if ch["key"] == "nhom_de_tu_gac_cong"), None)
    assert group_char is not None
    assert group_char["is_group"] is True
    assert group_char["group_size_hint"] == "2 người"
    assert group_char["role"] == "extra"


# ---------------------------------------------------------------------------
# 6. Auto role suggestion based on dialogue lines & frame counts
# ---------------------------------------------------------------------------
def test_suggest_character_roles_by_dialogue_counts(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=2)
    fid = frames[0]

    with Session(db.engine) as s:
        # C1: >= 3 lines, role_source='ai' -> main
        c1 = Character(project_id=pid, key="hero", name="Hero", role="supporting", role_source="ai")
        # C2: 1 line, role_source='ai' -> supporting
        c2 = Character(project_id=pid, key="friend", name="Friend", role="extra", role_source="ai")
        # C3: 0 lines, role_source='ai' -> extra
        c3 = Character(
            project_id=pid, key="bystander", name="Bystander", role="main", role_source="ai"
        )
        # C4: user edited -> stays as is
        c4 = Character(project_id=pid, key="boss", name="Boss", role="main", role_source="user")
        s.add_all([c1, c2, c3, c4])
        s.commit()

        # Add lines referencing real frame fid
        lines = [
            DialogueLine(
                chapter_id=cid,
                source_frame_id=fid,
                order=1,
                text="1",
                speaker_key="hero",
                text_raw="1",
            ),
            DialogueLine(
                chapter_id=cid,
                source_frame_id=fid,
                order=2,
                text="2",
                speaker_key="hero",
                text_raw="2",
            ),
            DialogueLine(
                chapter_id=cid,
                source_frame_id=fid,
                order=3,
                text="3",
                speaker_key="hero",
                text_raw="3",
            ),
            DialogueLine(
                chapter_id=cid,
                source_frame_id=fid,
                order=4,
                text="4",
                speaker_key="friend",
                text_raw="4",
            ),
        ]
        s.add_all(lines)
        s.commit()

        # Run suggest_character_roles
        stages.suggest_character_roles(s, pid)
        s.commit()

        s.refresh(c1)
        s.refresh(c2)
        s.refresh(c3)
        s.refresh(c4)

        assert c1.role == "main"
        assert c2.role == "supporting"
        assert c3.role == "extra"
        assert c4.role == "main"  # user preserved


# ---------------------------------------------------------------------------
# 7. Merge character transfers character_refs
# ---------------------------------------------------------------------------
def test_merge_character_transfers_refs(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=2)

    # Create src and dst characters
    src = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Lâm Phong (Bản phụ)", "gender": "male", "age_group": "young_adult"},
    ).json()
    dst = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Lâm Phong (Chính)", "gender": "male", "age_group": "young_adult"},
    ).json()

    src_id, dst_id = src["id"], dst["id"]

    # Add 2 refs to src
    client.post(
        f"/api/characters/{src_id}/refs/crop",
        json={"frame_id": frames[0], "x0": 0, "y0": 0, "x1": 80, "y1": 80},
    )
    client.post(
        f"/api/characters/{src_id}/refs/crop",
        json={"frame_id": frames[1], "x0": 0, "y0": 0, "x1": 80, "y1": 80},
    )

    # Add 1 ref to dst
    client.post(
        f"/api/characters/{dst_id}/refs/crop",
        json={"frame_id": frames[0], "x0": 20, "y0": 20, "x1": 100, "y1": 100},
    )

    assert len(client.get(f"/api/characters/{src_id}/refs").json()) == 2
    assert len(client.get(f"/api/characters/{dst_id}/refs").json()) == 1

    # Merge src into dst
    m_res = client.post(f"/api/characters/{src_id}/merge", json={"into_id": dst_id})
    assert m_res.status_code == 200

    # src is deleted
    assert client.get(f"/api/characters/{src_id}/refs").status_code == 404

    # dst now has all 3 refs
    dst_refs = client.get(f"/api/characters/{dst_id}/refs").json()
    assert len(dst_refs) == 3
    for r in dst_refs:
        assert r["character_id"] == dst_id
