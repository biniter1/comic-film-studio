import time

from fastapi.testclient import TestClient


def wait_job(c: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("succeeded", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish: {j}")


def new_chapter(c: TestClient, name: str = "Truyện test") -> tuple[str, str]:
    p = c.post("/api/projects", json={"name": name}).json()
    ch = c.post(f"/api/projects/{p['id']}/chapters", json={"title": "Chapter 1"}).json()
    return p["id"], ch["id"]


def upload(c: TestClient, cid: str, files: list[tuple[str, bytes]]) -> dict:
    r = c.post(
        f"/api/chapters/{cid}/import/files",
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )
    assert r.status_code == 200, r.text
    return wait_job(c, r.json()["id"])
