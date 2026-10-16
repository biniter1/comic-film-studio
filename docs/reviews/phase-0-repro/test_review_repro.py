import asyncio, threading
from pathlib import Path
import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.jobs.runner import JobRunner, JobService
from app.jobs.event_bus import event_bus
from app.models.job import Job

@pytest.fixture
def db(tmp_path: Path):
    e = create_engine(f"sqlite:///{(tmp_path/'t.db').as_posix()}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(e)
    return e, tmp_path

async def test_R1_event_lost_when_enqueued_from_thread(db):
    """FastAPI `def` endpoints run in a threadpool -> no running loop -> event silently dropped."""
    engine, _ = db
    svc = JobService(engine=engine)
    q = event_bus.subscribe()
    await asyncio.to_thread(svc.enqueue, "demo_sleep", {"duration_s": 1})
    await asyncio.sleep(0.2)
    got = q.qsize()
    event_bus.unsubscribe(q)
    assert got == 1, f"expected 1 job.updated event, got {got}"

async def test_R2_dependent_of_failed_job_stuck_forever(db):
    engine, d = db
    svc = JobService(engine=engine)
    r = JobRunner(engine=engine, data_dir=d, backoff_delays=[0.01])
    parent = svc.enqueue("demo_sleep", {"duration_s": 0, "fail": True, "fail_category": "permanent"})
    child = svc.enqueue("demo_sleep", {"duration_s": 0}, depends_on=[parent.id])
    await r.start(); await asyncio.sleep(2); await r.stop()
    with Session(engine) as s:
        p, c = s.get(Job, parent.id), s.get(Job, child.id)
        assert p.status == "failed"
        assert c.status != "queued" or getattr(c, "user_action_required", None), \
            f"child still silently '{c.status}' with no explanation"

async def test_R3_cancel_during_backoff_is_ignored(db):
    engine, d = db
    svc = JobService(engine=engine)
    r = JobRunner(engine=engine, data_dir=d, backoff_delays=[1.0])
    j = svc.enqueue("demo_sleep", {"duration_s": 0, "fail": True, "fail_category": "transient"}, max_attempts=3)
    await r.start(); await asyncio.sleep(0.8)   # now sleeping in backoff, status=running
    svc.cancel(j.id, runner=r)
    await asyncio.sleep(1.5); await r.stop()
    with Session(engine) as s:
        assert s.get(Job, j.id).status == "cancelled", s.get(Job, j.id).status


def test_R5_spa_route_path_traversal(tmp_path, monkeypatch):
    """GET /..%2f..%2f<file> must NOT return files outside frontend/dist; unknown /api/* must be 404 JSON."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    c = TestClient(create_app())
    for u in ["/..%2f..%2fbackend%2fpyproject.toml", "/%2e%2e/%2e%2e/backend/pyproject.toml"]:
        r = c.get(u)
        assert "comic-film-studio-backend" not in r.text, f"{u} leaked a file outside dist"
    r = c.get("/api/khong-ton-tai")
    assert r.status_code == 404 and "error" in r.json()
