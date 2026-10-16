"""test_review_repro.py — Ported from docs/reviews/phase-0-repro/test_review_repro.py
and extended with tests for B2, B4 (next_run_at), B5, B6.

Every assert here must pass after the phase-0-fixes changes.
"""

import asyncio
import time
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.jobs.event_bus import event_bus
from app.jobs.runner import JobRunner, JobService
from app.models.job import Job


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path):
    e = create_engine(
        f"sqlite:///{(tmp_path / 't.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(e)
    return e, tmp_path


# ---------------------------------------------------------------------------
# R1 — SSE events must be published even when enqueue() is called from a thread
# ---------------------------------------------------------------------------


async def test_R1_event_not_lost_when_enqueued_from_thread(db):
    """B1 fix: enqueue() called via asyncio.to_thread must still fire job.updated."""
    engine, _ = db
    svc = JobService(engine=engine)

    # Bind the current running loop so publish_threadsafe works
    event_bus.bind_loop(asyncio.get_running_loop())

    q = event_bus.subscribe()
    try:
        await asyncio.to_thread(svc.enqueue, "demo_sleep", {"duration_s": 1})
        await asyncio.sleep(0.2)
        got = q.qsize()
    finally:
        event_bus.unsubscribe(q)

    assert got >= 1, f"expected ≥1 job.updated event, got {got}"


# ---------------------------------------------------------------------------
# R2 — Dependent job of a failed parent must not stay silently queued
# ---------------------------------------------------------------------------


async def test_R2_dependent_of_failed_job_stuck_forever(db):
    """B3 fix: child of permanently-failed parent must get user_action_required set."""
    engine, d = db
    svc = JobService(engine=engine)
    r = JobRunner(engine=engine, data_dir=d, backoff_delays=[0.01])

    event_bus.bind_loop(asyncio.get_running_loop())

    parent = svc.enqueue("demo_sleep", {"duration_s": 0, "fail": True, "fail_category": "permanent"})
    child = svc.enqueue("demo_sleep", {"duration_s": 0}, depends_on=[parent.id])

    await r.start()
    await asyncio.sleep(2)
    await r.stop()

    with Session(engine) as s:
        p = s.get(Job, parent.id)
        c = s.get(Job, child.id)
        assert p is not None and c is not None
        assert p.status == "failed"
        # Child must not be silently queued without explanation
        assert c.status != "queued" or getattr(c, "user_action_required", None), (
            f"child still silently '{c.status}' with no explanation"
        )


# ---------------------------------------------------------------------------
# R3 — Cancel during backoff must have immediate effect
# ---------------------------------------------------------------------------


async def test_R3_cancel_during_backoff_is_honoured(db):
    """B4 fix: job in backoff (status=queued, next_run_at set) can be cancelled immediately."""
    engine, d = db
    svc = JobService(engine=engine)
    r = JobRunner(engine=engine, data_dir=d, backoff_delays=[5.0])  # long backoff

    event_bus.bind_loop(asyncio.get_running_loop())

    j = svc.enqueue(
        "demo_sleep",
        {"duration_s": 0, "fail": True, "fail_category": "transient"},
        max_attempts=3,
    )

    await r.start()
    # Let it fail once and enter backoff (status=queued, next_run_at set)
    await asyncio.sleep(0.8)

    # Cancel while in backoff
    svc.cancel(j.id, runner=r)
    await asyncio.sleep(0.5)
    await r.stop()

    with Session(engine) as s:
        final = s.get(Job, j.id)
        assert final is not None
        assert final.status == "cancelled", final.status


# ---------------------------------------------------------------------------
# R5 — SPA path traversal + /api/* 404 JSON
# ---------------------------------------------------------------------------


def test_R5_spa_route_path_traversal(monkeypatch):
    """B5 fix: path traversal must not leak files outside frontend/dist;
    unknown /api/* routes must return 404 JSON."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    c = TestClient(create_app())

    # Path traversal attempts — must NOT return pyproject.toml content
    for url in [
        "/..%2f..%2fbackend%2fpyproject.toml",
        "/%2e%2e/%2e%2e/backend/pyproject.toml",
    ]:
        r = c.get(url)
        assert "comic-film-studio-backend" not in r.text, f"{url} leaked a file outside dist"

    # /api/* that doesn't exist must be 404 JSON (not index.html 200)
    r = c.get("/api/khong-ton-tai")
    assert r.status_code == 404, r.status_code
    assert "error" in r.json(), r.text


# ---------------------------------------------------------------------------
# B2 — Sync handler (demo_cpu) must not block the event loop
# ---------------------------------------------------------------------------


async def test_B2_sync_handler_does_not_block_event_loop(db):
    """demo_cpu is a `def` handler — event loop must stay responsive while it runs."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    engine, d = db
    svc = JobService(engine=engine)
    r = JobRunner(engine=engine, data_dir=d, backoff_delays=[0.1])

    event_bus.bind_loop(asyncio.get_running_loop())

    # Enqueue a 3-second CPU job
    svc.enqueue("demo_cpu", {"duration_s": 3})
    await r.start()

    # Give the job time to start running
    await asyncio.sleep(0.5)

    # Now measure event loop responsiveness via health endpoint
    client = TestClient(create_app())
    t0 = time.monotonic()
    resp = client.get("/api/health")
    elapsed_ms = (time.monotonic() - t0) * 1000

    await r.stop()

    assert resp.status_code == 200, f"/api/health returned {resp.status_code}"
    assert elapsed_ms < 200, f"/api/health took {elapsed_ms:.0f}ms (> 200ms) — event loop was blocked"


# ---------------------------------------------------------------------------
# B4 — next_run_at: backoff does not hold a concurrency slot
# ---------------------------------------------------------------------------


async def test_B4_backoff_via_next_run_at_frees_slot(db):
    """Job in backoff must have status=queued (not running) so it does not hold a slot."""
    engine, d = db
    svc = JobService(engine=engine)
    r = JobRunner(engine=engine, data_dir=d, backoff_delays=[5.0])  # very long backoff

    event_bus.bind_loop(asyncio.get_running_loop())

    j = svc.enqueue(
        "demo_sleep",
        {"duration_s": 0, "fail": True, "fail_category": "transient"},
        max_attempts=3,
    )

    await r.start()
    await asyncio.sleep(0.8)  # let it fail once and enter backoff
    await r.stop()

    with Session(engine) as s:
        job = s.get(Job, j.id)
        assert job is not None
        # After first transient failure, job must be queued with next_run_at set
        assert job.status == "queued", f"expected queued (in backoff), got {job.status}"
        assert job.next_run_at is not None, "next_run_at must be set during backoff"
        assert job.attempts == 1, f"attempts should be 1, got {job.attempts}"


# ---------------------------------------------------------------------------
# B6 — alembic upgrade head on a fresh DB must create all columns
# ---------------------------------------------------------------------------


def test_B6_alembic_upgrade_creates_all_columns(tmp_path: Path):
    """B6 fix: upgrade head on an empty DB must create jobs table with next_run_at."""
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig
    from sqlalchemy import inspect as sa_inspect, create_engine as sa_create_engine

    db_file = tmp_path / "fresh.db"
    alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    assert alembic_ini.exists(), f"alembic.ini not found at {alembic_ini}"

    cfg = AlembicConfig(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")

    alembic_command.upgrade(cfg, "head")

    eng = sa_create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    inspector = sa_inspect(eng)
    assert "jobs" in inspector.get_table_names(), "jobs table missing after upgrade"

    col_names = {c["name"] for c in inspector.get_columns("jobs")}
    required = {
        "id", "type", "status", "depends_on", "input_hash",
        "attempts", "max_attempts", "progress", "log_path",
        "error_category", "error_message", "user_action_required",
        "payload", "next_run_at", "created_at", "started_at", "finished_at",
    }
    missing = required - col_names
    assert not missing, f"Missing columns after upgrade head: {missing}"

