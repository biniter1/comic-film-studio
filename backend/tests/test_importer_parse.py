import io

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from PIL import Image

from app.importer import url as urlimp
from app.importer.url import SiteProfile, extract_image_urls
from app.main import create_app
from tests.apiutil import new_chapter, wait_job
from tests.imgutil import noise_block, page

HTML = """
<html><body>
<header><img src="/static/logo.png"><img src="/img/avatar-user.jpg"></header>
<div class="reading">
  <img src="data:image/gif;base64,R0lGOD" data-src="https://cdn.example/ch1/001.jpg">
  <img data-original="/ch1/002.jpg">
  <img srcset="/ch1/003.jpg 1x, /ch1/003@2x.jpg 2x">
  <img src="https://cdn.example/ch1/001.jpg">
  <img src="/icons/spinner.gif">
</div>
<footer><img src="/ads/banner-top.png"></footer>
</body></html>
"""


def test_generic_extraction_order_lazy_attrs_and_junk_filter():
    urls = extract_image_urls(HTML, "https://truyen.example/manga/ch1")
    assert urls == [
        "https://cdn.example/ch1/001.jpg",
        "https://truyen.example/ch1/002.jpg",
        "https://truyen.example/ch1/003.jpg",
    ]


def test_profile_selector_limits_to_reader():
    prof = SiteProfile(domain="truyen.example", image_selector="div.reading img")
    urls = extract_image_urls(HTML, "https://truyen.example/manga/ch1", prof)
    assert "https://truyen.example/static/logo.png" not in urls
    assert len(urls) == 3


def _jpeg(seed: int) -> bytes:
    b = io.BytesIO()
    page([noise_block(400, seed=seed)]).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def c(monkeypatch):
    # pretend every host resolves to a public IP (no real DNS / network in tests)
    import ipaddress

    def fake_resolve(host: str) -> list[str]:
        try:
            ipaddress.ip_address(host)
            return [host]  # IP literals keep their real value (must still be blocked)
        except ValueError:
            return ["93.184.216.34"]

    monkeypatch.setattr(urlimp, "_resolve", fake_resolve)
    with TestClient(create_app()) as client:
        yield client


def test_import_url_end_to_end_with_referer(c):
    _, cid = new_chapter(c)
    seen_referers = []

    def img(seed):
        def handler(request: httpx.Request):
            seen_referers.append(request.headers.get("referer"))
            return httpx.Response(200, content=_jpeg(seed), headers={"content-type": "image/jpeg"})

        return handler

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://truyen.example/manga/ch1").respond(200, html=HTML)
        mock.get("https://cdn.example/ch1/001.jpg").mock(side_effect=img(1))
        mock.get("https://truyen.example/ch1/002.jpg").mock(side_effect=img(2))
        mock.get("https://truyen.example/ch1/003.jpg").respond(404)
        r = c.post(
            f"/api/chapters/{cid}/import/url", json={"url": "https://truyen.example/manga/ch1"}
        )
        job = wait_job(c, r.json()["id"])
    assert job["status"] == "succeeded", job
    pages = c.get(f"/api/chapters/{cid}/pages").json()
    assert len(pages) == 2
    assert pages[0]["original_name"].startswith("0001_")  # DOM order kept
    assert set(seen_referers) == {"https://truyen.example/manga/ch1"}
    report = c.get(f"/api/chapters/{cid}/import/report").json()
    assert any("003.jpg" in r["name"] for r in report["rejected"])


def test_import_url_403_fails_with_folder_hint(c):
    _, cid = new_chapter(c)
    with respx.mock() as mock:
        mock.get("https://locked.example/ch").respond(403)
        r = c.post(f"/api/chapters/{cid}/import/url", json={"url": "https://locked.example/ch"})
        job = wait_job(c, r.json()["id"])
    assert job["status"] == "failed"
    assert job["error_category"] == "permanent"
    assert "thư mục" in (job["user_action_required"] or "")


def test_import_url_redirect_to_private_ip_is_blocked(c, monkeypatch):
    _, cid = new_chapter(c)
    with respx.mock() as mock:
        mock.get("https://ok.example/ch").respond(
            302, headers={"location": "http://127.0.0.1/secret"}
        )
        r = c.post(f"/api/chapters/{cid}/import/url", json={"url": "https://ok.example/ch"})
        job = wait_job(c, r.json()["id"])
    assert job["status"] == "failed"
    assert "nội bộ" in job["error_message"]


def test_import_url_rejected_up_front_for_private_target(c):
    _, cid = new_chapter(c)
    r = c.post(
        f"/api/chapters/{cid}/import/url", json={"url": "http://127.0.0.1:8765/api/projects"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSAFE_URL"


def test_page_without_images_fails_clearly(c):
    _, cid = new_chapter(c)
    with respx.mock() as mock:
        mock.get("https://js.example/ch").respond(200, html="<html><div id=app></div></html>")
        r = c.post(f"/api/chapters/{cid}/import/url", json={"url": "https://js.example/ch"})
        job = wait_job(c, r.json()["id"])
    assert job["status"] == "failed" and "JavaScript" in job["error_message"]


def test_image_used_imported_names():
    assert Image  # keep import used
