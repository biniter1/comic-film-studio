import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from tests.apiutil import new_chapter, upload, wait_job
from tests.imgutil import gutter, noise_block, page, two_pages_with_split_panel


@pytest.fixture
def c():
    with TestClient(create_app()) as client:
        yield client


def png_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    b = io.BytesIO()
    img.save(b, fmt)
    return b.getvalue()


# --- projects / chapters -------------------------------------------------------
def test_project_crud_and_delete_requires_confirm(c):
    p = c.post("/api/projects", json={"name": "Tu Tiên"}).json()
    assert c.get(f"/api/projects/{p['id']}").json()["name"] == "Tu Tiên"
    assert (
        c.patch(f"/api/projects/{p['id']}", json={"name": "Tu Tiên 2"}).json()["name"]
        == "Tu Tiên 2"
    )
    assert any(x["id"] == p["id"] for x in c.get("/api/projects").json())
    r = c.delete(f"/api/projects/{p['id']}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "CONFIRM_REQUIRED"
    assert c.delete(f"/api/projects/{p['id']}?confirm=true").status_code == 200
    assert c.get(f"/api/projects/{p['id']}").status_code == 404


def test_empty_name_rejected(c):
    r = c.post("/api/projects", json={"name": "   "})
    assert r.status_code == 422


# --- import local --------------------------------------------------------------
def test_import_local_natural_sort_rejects_and_duplicates(c):
    _, cid = new_chapter(c)
    good = lambda seed: png_bytes(page([noise_block(400, seed=seed)]))  # noqa: E731
    files = [
        ("10.png", good(10)),
        ("2.png", good(2)),
        ("1.png", good(1)),
        ("z-copy-of-1.png", good(1)),  # same content as 1.png
        ("broken.jpg", b"not an image at all"),
        ("tiny.png", png_bytes(Image.new("RGB", (120, 400), "red"))),
    ]
    job = upload(c, cid, files)
    assert job["status"] == "succeeded", job
    pages = c.get(f"/api/chapters/{cid}/pages").json()
    assert [p["original_name"] for p in pages] == ["1.png", "2.png", "10.png"]
    report = c.get(f"/api/chapters/{cid}/import/report").json()
    rejected = {r["name"]: r["reason"] for r in report["rejected"]}
    assert "broken.jpg" in rejected and "tiny.png" in rejected
    assert "quá nhỏ" in rejected["tiny.png"]
    assert [d["name"] for d in report["duplicates"]] == ["z-copy-of-1.png"]
    # previews are served
    assert c.get(pages[0]["preview_url"]).status_code == 200
    assert c.get(f"/api/chapters/{cid}").json()["status"] == "imported"


def test_reimport_same_files_is_idempotent(c):
    _, cid = new_chapter(c)
    data = [("a.png", png_bytes(page([noise_block(300, seed=7)])))]
    upload(c, cid, data)
    upload(c, cid, data)
    assert len(c.get(f"/api/chapters/{cid}/pages").json()) == 1


def test_reorder_and_exclude_pages(c):
    _, cid = new_chapter(c)
    upload(c, cid, [(f"{i}.png", png_bytes(page([noise_block(300, seed=i)]))) for i in (1, 2, 3)])
    pages = c.get(f"/api/chapters/{cid}/pages").json()
    order = [
        {"id": pages[2]["id"]},
        {"id": pages[0]["id"], "excluded": True},
        {"id": pages[1]["id"]},
    ]
    out = c.patch(f"/api/chapters/{cid}/pages", json={"pages": order}).json()
    assert [p["original_name"] for p in out] == ["3.png", "1.png", "2.png"]
    assert out[1]["status"] == "excluded"
    bad = c.patch(f"/api/chapters/{cid}/pages", json={"pages": order[:2]})
    assert bad.status_code == 422


# --- frames ----------------------------------------------------------------------
def _chapter_with_frames(c, tmp_path) -> str:
    _, cid = new_chapter(c)
    files = [(p.name, p.read_bytes()) for p in two_pages_with_split_panel(tmp_path)]
    upload(c, cid, files)
    job = c.post(f"/api/chapters/{cid}/frames/auto").json()
    assert wait_job(c, job["id"])["status"] == "succeeded"
    return cid


def test_auto_frames_reassemble_panel_across_pages(c, tmp_path):
    cid = _chapter_with_frames(c, tmp_path)
    data = c.get(f"/api/chapters/{cid}/frames").json()
    assert data["status"] == "frames_draft"
    heights = [f["y1"] - f["y0"] for f in data["frames"]]
    assert heights[:2] == [400, 600] and len(heights) == 3
    assert len(data["strip"]["pages"]) == 2
    img = Image.open(io.BytesIO(c.get(data["frames"][1]["url"]).content))
    assert img.size == (600, 600)


def test_edit_frames_merge_split_and_validation(c, tmp_path):
    cid = _chapter_with_frames(c, tmp_path)
    before = c.get(f"/api/chapters/{cid}/frames").json()["frames"]
    f0, f1, f2 = before
    # merge first two frames
    merged = [{"y0": f0["y0"], "y1": f1["y1"]}, {"y0": f2["y0"], "y1": f2["y1"]}]
    after = c.put(f"/api/chapters/{cid}/frames", json={"frames": merged}).json()["frames"]
    assert len(after) == 2
    assert after[0]["origin"] == "manual"
    assert after[1]["asset_id"] == f2["asset_id"], "unchanged frame keeps its crop"
    # old frame assets are kept (versions), still downloadable
    assert c.get(f0["url"]).status_code == 200
    # split the merged one again
    mid = (f0["y0"] + f1["y1"]) // 2
    split = [
        {"y0": f0["y0"], "y1": mid},
        {"y0": mid, "y1": f1["y1"]},
        {"y0": f2["y0"], "y1": f2["y1"]},
    ]
    assert len(c.put(f"/api/chapters/{cid}/frames", json={"frames": split}).json()["frames"]) == 3
    # overlapping → 422
    bad = [{"y0": 0, "y1": 500}, {"y0": 400, "y1": 900}]
    r = c.put(f"/api/chapters/{cid}/frames", json={"frames": bad})
    assert r.status_code == 422 and "chồng lấn" in r.json()["error"]["message_vi"]


def test_approve_frames_and_page_change_invalidates(c, tmp_path):
    cid = _chapter_with_frames(c, tmp_path)
    assert c.post(f"/api/chapters/{cid}/frames/approve").json()["status"] == "frames_approved"
    pages = c.get(f"/api/chapters/{cid}/pages").json()
    c.patch(
        f"/api/chapters/{cid}/pages", json={"pages": [{"id": p["id"]} for p in reversed(pages)]}
    )
    ch = c.get(f"/api/chapters/{cid}").json()
    assert ch["status"] == "imported" and ch["frame_count"] == 0


def test_approve_without_frames_is_409(c):
    _, cid = new_chapter(c)
    assert c.post(f"/api/chapters/{cid}/frames/approve").status_code == 409


def test_asset_404_for_unknown_id(c):
    r = c.get("/api/assets/ANOPE/file")
    assert r.status_code == 404 and r.json()["error"]["code"] == "ASSET_NOT_FOUND"


def test_unused_helpers_render():
    # keep helper import used (gutter) for linters
    assert gutter(1).shape == (1, 600, 3)


def test_drop_a_frame_leaves_a_gap(c, tmp_path):
    """Removing a frame (ad / translator banner) = PUT without it; gaps are allowed."""
    cid = _chapter_with_frames(c, tmp_path)
    f0, f1, f2 = c.get(f"/api/chapters/{cid}/frames").json()["frames"]
    body = {"frames": [{"y0": f0["y0"], "y1": f0["y1"]}, {"y0": f2["y0"], "y1": f2["y1"]}]}
    out = c.put(f"/api/chapters/{cid}/frames", json=body).json()["frames"]
    assert [f["asset_id"] for f in out] == [f0["asset_id"], f2["asset_id"]]
    assert [f["idx"] for f in out] == [1, 2]
    assert c.post(f"/api/chapters/{cid}/frames/approve").status_code == 200
