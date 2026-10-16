"""Tests for Phase 2b: Story Bible, outfits, locations, consistency sheet bundles,
uploads (SPEC §4.6)."""

import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import db
from app.main import create_app
from app.models.project import Asset
from tests.analysisutil import Script, chapter_with_frames, line, use_fake


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CFS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CFS_SQLITE_URL", f"sqlite:///{tmp_path / 'cfs.db'}")
    app = create_app()
    with TestClient(app) as c:
        yield c


def _png(w: int = 400, h: int = 300, color: tuple[int, int, int] = (120, 150, 180)) -> bytes:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Outfits CRUD & Default outfit rules
# ---------------------------------------------------------------------------
def test_outfit_crud_and_default_protection(client: TestClient):
    p = client.post("/api/projects", json={"name": "Dự án Outfits"}).json()
    pid = p["id"]

    # Creating a character automatically creates a default outfit
    c_res = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Lâm Phong", "gender": "male", "age_group": "young_adult"},
    )
    assert c_res.status_code == 201
    char = c_res.json()
    chid = char["id"]

    outfits = client.get(f"/api/characters/{chid}/outfits").json()
    assert len(outfits) == 1
    default_outfit = outfits[0]
    assert default_outfit["key"] == "default"
    assert default_outfit["is_default"] is True
    assert default_outfit["sheet_status"] == "missing"

    # Cannot delete the only default outfit
    del_res = client.delete(f"/api/outfits/{default_outfit['id']}")
    assert del_res.status_code == 409
    assert del_res.json()["error"]["code"] in (
        "CANNOT_DELETE_LAST_OUTFIT",
        "CANNOT_DELETE_DEFAULT_OUTFIT",
    )

    # Add a second outfit
    o2_res = client.post(
        f"/api/characters/{chid}/outfits",
        json={
            "name_vi": "Hắc Bào Chiến Giáp",
            "outfit_lock": "black armor robe with gold trim",
            "short_id": "the armored man",
            "is_default": False,
        },
    )
    assert o2_res.status_code == 201
    o2 = o2_res.json()
    assert o2["key"] == "hac_bao_chien_giap"
    assert o2["is_default"] is False

    # Still cannot delete the default outfit (it is the last default)
    del_default = client.delete(f"/api/outfits/{default_outfit['id']}")
    assert del_default.status_code == 409

    # Update outfit 2 to be default
    patch_res = client.patch(
        f"/api/outfits/{o2['id']}",
        json={"is_default": True, "name_vi": "Hắc Bào Chiến Giáp (Mới)"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_default"] is True
    assert patch_res.json()["name_vi"] == "Hắc Bào Chiến Giáp (Mới)"

    # Now default_outfit is no longer default, so it can be deleted
    del_res2 = client.delete(f"/api/outfits/{default_outfit['id']}")
    assert del_res2.status_code == 200
    assert del_res2.json()["deleted"] == default_outfit["id"]

    # Now o2 is the only remaining outfit, so it cannot be deleted
    del_last = client.delete(f"/api/outfits/{o2['id']}")
    assert del_last.status_code == 409


# ---------------------------------------------------------------------------
# Location CRUD
# ---------------------------------------------------------------------------
def test_location_crud(client: TestClient):
    p = client.post("/api/projects", json={"name": "Dự án Locations"}).json()
    pid = p["id"]

    # Create location
    loc_res = client.post(
        f"/api/projects/{pid}/locations",
        json={
            "name_vi": "Thanh Vân Đại Điện",
            "aliases": ["Đại điện", "Thanh Vân Điện"],
            "location_lock": "grand ancient Daoist temple hall, high carved pillars, mystical mist",
            "ref_frame_ids": [],
        },
    )
    assert loc_res.status_code == 201
    loc = loc_res.json()
    assert loc["key"] == "thanh_van_dai_dien"
    assert loc["sheet_status"] == "missing"
    lid = loc["id"]

    # List locations
    locs = client.get(f"/api/projects/{pid}/locations").json()
    assert len(locs) == 1
    assert locs[0]["name_vi"] == "Thanh Vân Đại Điện"

    # Patch location
    patch_res = client.patch(
        f"/api/locations/{lid}",
        json={"location_lock": "updated grand hall"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["location_lock"] == "updated grand hall"

    # Delete location
    del_res = client.delete(f"/api/locations/{lid}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] == lid
    assert len(client.get(f"/api/projects/{pid}/locations").json()) == 0


# ---------------------------------------------------------------------------
# Sheet Bundle: 409 when ref_frame_ids is empty, correct zip & prompt when set
# ---------------------------------------------------------------------------
def test_sheet_bundle_outfit_and_location(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=3)

    # Create character
    c = client.post(
        f"/api/projects/{pid}/characters",
        json={
            "name": "Lâm Phong",
            "look_lock": "young man, black ponytail, sharp red eyes",
            "ref_frame_ids": [],
        },
    ).json()
    chid = c["id"]
    outfits = client.get(f"/api/characters/{chid}/outfits").json()
    oid = outfits[0]["id"]

    # 409 when ref_frame_ids is empty
    b1 = client.get(f"/api/outfits/{oid}/sheet-bundle")
    assert b1.status_code == 409
    assert "Chọn 2–4 khung tham chiếu trước" in b1.json()["error"]["message_vi"]

    # Set 2 ref frames on character
    patch_c = client.patch(
        f"/api/characters/{chid}",
        json={"ref_frame_ids": [frames[0], frames[1]]},
    )
    assert patch_c.status_code == 200

    # Also set outfit_lock
    client.patch(
        f"/api/outfits/{oid}",
        json={"outfit_lock": "white inner robe, black sleeveless coat"},
    )

    # Now sheet bundle succeeds
    b2 = client.get(f"/api/outfits/{oid}/sheet-bundle")
    assert b2.status_code == 200
    assert b2.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(b2.content)) as zf:
        namelist = zf.namelist()
        assert "prompt.txt" in namelist
        assert "HUONG_DAN.txt" in namelist
        assert f"01_{frames[0]}.png" in namelist
        assert f"02_{frames[1]}.png" in namelist

        prompt_txt = zf.read("prompt.txt").decode("utf-8")
        assert "young man, black ponytail, sharp red eyes" in prompt_txt
        assert "white inner robe, black sleeveless coat" in prompt_txt

        guide_txt = zf.read("HUONG_DAN.txt").decode("utf-8")
        assert "Gemini" in guide_txt

    # Test Location sheet bundle
    loc = client.post(
        f"/api/projects/{pid}/locations",
        json={
            "name_vi": "Dược Viên",
            "location_lock": "lush spiritual herb garden, glowing plants, wooden fences",
            "ref_frame_ids": [],
        },
    ).json()
    lid = loc["id"]

    # 409 when empty
    loc_b1 = client.get(f"/api/locations/{lid}/sheet-bundle")
    assert loc_b1.status_code == 409

    # Set ref frames
    client.patch(f"/api/locations/{lid}", json={"ref_frame_ids": [frames[2]]})
    loc_b2 = client.get(f"/api/locations/{lid}/sheet-bundle")
    assert loc_b2.status_code == 200

    with zipfile.ZipFile(io.BytesIO(loc_b2.content)) as zf:
        namelist = zf.namelist()
        assert "prompt.txt" in namelist
        assert f"01_{frames[2]}.png" in namelist
        prompt_txt = zf.read("prompt.txt").decode("utf-8")
        assert "establishing wide shot + reverse angle, no characters" in prompt_txt
        assert "lush spiritual herb garden, glowing plants, wooden fences" in prompt_txt


# ---------------------------------------------------------------------------
# Upload Sheet: validation, versions (v1, v2 kept), approve & reject
# ---------------------------------------------------------------------------
def test_upload_sheet_versioning_and_approval(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=2)
    c = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Tiêu Viêm"},
    ).json()
    outfit = client.get(f"/api/characters/{c['id']}/outfits").json()[0]
    oid = outfit["id"]

    # Upload corrupt file -> 422
    bad_upload = client.post(
        f"/api/outfits/{oid}/sheet",
        files={"file": ("bad.png", b"not-a-valid-image", "image/png")},
    )
    assert bad_upload.status_code == 422
    assert bad_upload.json()["error"]["code"] == "INVALID_IMAGE"

    # Upload valid image 1
    png1 = _png(400, 300, (200, 50, 50))
    up1 = client.post(
        f"/api/outfits/{oid}/sheet",
        files={"file": ("sheet_take1.png", png1, "image/png")},
    )
    assert up1.status_code == 200
    res1 = up1.json()
    assert res1["sheet_status"] == "pending"
    assert res1["sheet_url"] is not None
    asset1_id = res1["sheet_asset_id"]

    # Check asset 1 in DB
    from sqlmodel import Session

    with Session(db.engine) as s:
        a1 = s.get(Asset, asset1_id)
        assert a1 is not None
        assert a1.version == 1
        assert a1.path.endswith("sheet_v1.png")
        assert a1.approval == "pending"

    # Approve sheet 1
    app1 = client.post(f"/api/outfits/{oid}/sheet/approve")
    assert app1.status_code == 200
    assert app1.json()["sheet_status"] == "approved"

    with Session(db.engine) as s:
        a1 = s.get(Asset, asset1_id)
        assert a1.approval == "approved"

    # Upload valid image 2 (new sheet version)
    png2 = _png(400, 300, (50, 200, 50))
    up2 = client.post(
        f"/api/outfits/{oid}/sheet",
        files={"file": ("sheet_take2.png", png2, "image/png")},
    )
    assert up2.status_code == 200
    res2 = up2.json()
    assert res2["sheet_status"] == "pending"
    asset2_id = res2["sheet_asset_id"]
    assert asset2_id != asset1_id

    # Verify sheet_v2 was created, and v1 still exists!
    with Session(db.engine) as s:
        a2 = s.get(Asset, asset2_id)
        assert a2.version == 2
        assert a2.path.endswith("sheet_v2.png")
        # v1 is still in DB
        a1_refreshed = s.get(Asset, asset1_id)
        assert a1_refreshed is not None
        assert a1_refreshed.version == 1

    # Reject sheet 2 -> reverts to previous approved version (v1)
    rej = client.post(f"/api/outfits/{oid}/sheet/reject")
    assert rej.status_code == 200
    assert rej.json()["sheet_status"] == "approved"
    assert rej.json()["sheet_asset_id"] == asset1_id

    # Reject sheet 1 -> now no approved sheet remains -> sheet_status = missing
    rej_last = client.post(f"/api/outfits/{oid}/sheet/reject")
    assert rej_last.status_code == 200
    assert rej_last.json()["sheet_status"] == "missing"


# ---------------------------------------------------------------------------
# Frame Suggestions based on Frame.reading["characters"]
# ---------------------------------------------------------------------------
def test_frame_suggestions_from_read_analysis(client: TestClient):
    pid, cid, frames = chapter_with_frames(client, n=3)

    # Set up scripted fake provider:
    # frame 0: scene with lam_phong
    # frame 1: dialogue_only with lam_phong
    # frame 2: scene with another_char
    script = Script(
        frames={
            frames[0]: {
                "type": "scene",
                "texts": [line(1, "Ta là Lâm Phong!", speaker="lam_phong")],
            },
            frames[1]: {
                "type": "dialogue_only",
                "texts": [line(1, "Chạy đi đâu?", speaker="lam_phong", belongs_to="prev")],
            },
            frames[2]: {
                "type": "scene",
                "texts": [line(1, "Ngươi là ai?", speaker="tieu_viem")],
            },
        },
        new_characters=[
            {"key": "lam_phong", "name": "Lâm Phong", "gender": "male", "age_group": "young_adult"},
            {"key": "tieu_viem", "name": "Tiêu Viêm", "gender": "male", "age_group": "young_adult"},
        ],
    )
    # Give frame 0 and frame 1 the reading character "lam_phong"
    orig_read = script.read_answer

    def read_with_chars(req):
        data = orig_read(req)
        for fr in data["frames"]:
            if fr["frame_id"] == frames[0]:
                fr["characters"] = ["lam_phong"]
            elif fr["frame_id"] == frames[1]:
                fr["characters"] = ["lam_phong"]
            elif fr["frame_id"] == frames[2]:
                fr["characters"] = ["tieu_viem"]
        return data

    script.read_answer = read_with_chars
    use_fake(script)

    # Run analysis
    res = client.post(f"/api/chapters/{cid}/analysis/read", json={"mode": "api"}).json()
    # Read finished
    from tests.apiutil import wait_job

    wait_job(client, res["jobs"][0]["id"])

    # Characters were created by analysis
    chars = client.get(f"/api/projects/{pid}/characters").json()
    lp = next(c for c in chars if c["key"] == "lam_phong")

    # Call frame-suggestions
    sugg = client.get(f"/api/characters/{lp['id']}/frame-suggestions").json()
    assert len(sugg) == 2
    suggested_ids = [s["id"] for s in sugg]
    # frame 0 (scene) is prioritized over frame 1 (dialogue_only)
    assert suggested_ids[0] == frames[0]
    assert suggested_ids[1] == frames[1]
    assert sugg[0]["image_url"].startswith("/api/assets/")


def test_get_project_bible(client: TestClient):
    p = client.post("/api/projects", json={"name": "Dự án Bible"}).json()
    pid = p["id"]

    client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Lâm Phong", "gender": "male", "age_group": "young_adult"},
    )
    client.post(
        f"/api/projects/{pid}/locations",
        json={"name_vi": "Huyền Thiên Tông", "location_lock": "floating mountain sects"},
    )

    bible = client.get(f"/api/projects/{pid}/bible").json()
    assert bible["project_id"] == pid
    assert len(bible["characters"]) == 1
    assert len(bible["characters"][0]["outfits"]) == 1
    assert len(bible["locations"]) == 1
    assert bible["locations"][0]["name_vi"] == "Huyền Thiên Tông"


def test_outfit_sheet_independent_version_and_rejection(client: TestClient):
    p = client.post("/api/projects", json={"name": "Dự án Outfits Substring"}).json()
    pid = p["id"]
    char = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Lâm Phong", "gender": "male"},
    ).json()
    chid = char["id"]

    outfits = client.get(f"/api/characters/{chid}/outfits").json()
    o_default = outfits[0]
    assert o_default["key"] == "default"

    # Add second outfit with key "default_2"
    o2_res = client.post(
        f"/api/characters/{chid}/outfits",
        json={"name_vi": "Default Two", "key": "default_2"},
    )
    assert o2_res.status_code == 201
    o_default_2 = o2_res.json()
    assert o_default_2["key"] == "default_2"

    # Upload and approve sheet for default_2 first
    png2 = _png(400, 300, (10, 20, 30))
    up2 = client.post(
        f"/api/outfits/{o_default_2['id']}/sheet",
        files={"file": ("sheet.png", png2, "image/png")},
    )
    assert up2.status_code == 200
    res2 = up2.json()
    assert res2["sheet_status"] == "pending"
    app2 = client.post(f"/api/outfits/{o_default_2['id']}/sheet/approve")
    assert app2.status_code == 200
    assert app2.json()["sheet_status"] == "approved"
    sheet2_asset_id = app2.json()["sheet_asset_id"]

    # Upload sheet for default -> should be sheet_v1 (independent of default_2)
    png1 = _png(400, 300, (40, 50, 60))
    up1 = client.post(
        f"/api/outfits/{o_default['id']}/sheet",
        files={"file": ("sheet.png", png1, "image/png")},
    )
    assert up1.status_code == 200
    res1 = up1.json()
    sheet1_asset_id = res1["sheet_asset_id"]

    from sqlmodel import Session

    with Session(db.engine) as s:
        a1 = s.get(Asset, sheet1_asset_id)
        assert a1 is not None
        assert a1.version == 1
        assert a1.path.endswith("refs/lam_phong/default/sheet_v1.png")
        a2 = s.get(Asset, sheet2_asset_id)
        assert a2 is not None
        assert a2.version == 1
        assert a2.path.endswith("refs/lam_phong/default_2/sheet_v1.png")

    # Reject sheet of default (which has no previous approved sheet)
    # -> MUST NOT point to default_2's sheet
    rej = client.post(f"/api/outfits/{o_default['id']}/sheet/reject")
    assert rej.status_code == 200
    rej_data = rej.json()
    assert rej_data["sheet_status"] == "missing"
    assert rej_data["sheet_asset_id"] != sheet2_asset_id


def test_merge_characters_preserves_outfits_and_sheets(client: TestClient):
    p = client.post("/api/projects", json={"name": "Dự án Merge Outfits"}).json()
    pid = p["id"]

    # Char 1: Lam Phong (destination)
    c1 = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Lâm Phong", "gender": "male"},
    ).json()
    c1_outfits = client.get(f"/api/characters/{c1['id']}/outfits").json()
    c1_def = c1_outfits[0]

    # Char 2: Phong Nhi (source)
    c2 = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Phong Nhi", "gender": "male"},
    ).json()
    c2_outfits = client.get(f"/api/characters/{c2['id']}/outfits").json()
    c2_def = c2_outfits[0]

    # Upload and approve sheet for c1 default
    up1 = client.post(
        f"/api/outfits/{c1_def['id']}/sheet",
        files={"file": ("sheet1.png", _png(400, 300, (10, 10, 10)), "image/png")},
    )
    assert up1.status_code == 200
    app1 = client.post(f"/api/outfits/{c1_def['id']}/sheet/approve").json()
    c1_sheet_id = app1["sheet_asset_id"]
    assert c1_sheet_id is not None

    # Upload and approve sheet for c2 default
    up2 = client.post(
        f"/api/outfits/{c2_def['id']}/sheet",
        files={"file": ("sheet2.png", _png(400, 300, (20, 20, 20)), "image/png")},
    )
    assert up2.status_code == 200
    app2 = client.post(f"/api/outfits/{c2_def['id']}/sheet/approve").json()
    c2_sheet_id = app2["sheet_asset_id"]
    assert c2_sheet_id is not None

    # Merge c2 into c1
    m_res = client.post(
        f"/api/characters/{c2['id']}/merge",
        json={"into_id": c1["id"]},
    )
    assert m_res.status_code == 200

    # Query destination outfits
    outfits = client.get(f"/api/characters/{c1['id']}/outfits").json()
    assert len(outfits) == 2

    # Exactly 1 default outfit
    defaults = [o for o in outfits if o["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["key"] == "default"
    assert defaults[0]["sheet_asset_id"] == c1_sheet_id

    # The other outfit was renamed with prefix f"{src.key}_{o.key}"
    non_defaults = [o for o in outfits if not o["is_default"]]
    assert len(non_defaults) == 1
    merged_o = non_defaults[0]
    assert merged_o["key"] == f"{c2['key']}_default"
    assert merged_o["sheet_asset_id"] == c2_sheet_id
    assert merged_o["sheet_status"] == "approved"


def test_upload_sheet_file_too_large_413(client: TestClient, monkeypatch):
    import app.api.bible

    # Monkeypatch MAX_IMAGE_BYTES in api module to a small size for fast testing (e.g. 100 bytes)
    monkeypatch.setattr(app.api.bible, "MAX_IMAGE_BYTES", 100)

    p = client.post("/api/projects", json={"name": "Dự án 413"}).json()
    pid = p["id"]
    char = client.post(
        f"/api/projects/{pid}/characters",
        json={"name": "Lâm Phong", "gender": "male"},
    ).json()
    outfits = client.get(f"/api/characters/{char['id']}/outfits").json()
    oid = outfits[0]["id"]

    # Send 200 bytes > 100 bytes
    res = client.post(
        f"/api/outfits/{oid}/sheet",
        files={"file": ("huge.png", b"x" * 200, "image/png")},
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert "Ảnh quá lớn" in res.json()["error"]["message_vi"]
