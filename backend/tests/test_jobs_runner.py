import asyncio
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.jobs.runner import JobRunner, JobService
from app.models.job import Job


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine, tmp_path


@pytest.mark.asyncio
async def test_demo_job_succeeds(test_db):
    engine, data_dir = test_db
    service = JobService(engine=engine)
    runner = JobRunner(engine=engine, concurrency=2, data_dir=data_dir, backoff_delays=[0.05, 0.1])

    job = service.enqueue("demo_sleep", payload={"duration_s": 1})
    assert job.status == "queued"

    await runner.start()

    # Wait for completion
    for _ in range(30):
        await asyncio.sleep(0.2)
        with Session(engine) as session:
            j = session.get(Job, job.id)
            if j and j.status == "succeeded":
                assert j.progress == 1.0
                assert j.finished_at is not None
                break
    else:
        pytest.fail("Job did not succeed in time")

    await runner.stop()


@pytest.mark.asyncio
async def test_job_depends_on(test_db):
    engine, data_dir = test_db
    service = JobService(engine=engine)
    runner = JobRunner(engine=engine, concurrency=2, data_dir=data_dir, backoff_delays=[0.05, 0.1])

    parent = service.enqueue("demo_sleep", payload={"duration_s": 1})
    child = service.enqueue("demo_sleep", payload={"duration_s": 1}, depends_on=[parent.id])

    await runner.start()

    # Wait for child completion
    for _ in range(50):
        await asyncio.sleep(0.2)
        with Session(engine) as session:
            c = session.get(Job, child.id)
            p = session.get(Job, parent.id)
            if c and c.status == "succeeded":
                assert p.status == "succeeded"
                assert c.started_at >= p.finished_at
                break
    else:
        pytest.fail("Child job did not complete after parent")

    await runner.stop()


@pytest.mark.asyncio
async def test_transient_error_retry(test_db):
    engine, data_dir = test_db
    service = JobService(engine=engine)
    runner = JobRunner(
        engine=engine,
        concurrency=1,
        data_dir=data_dir,
        backoff_delays=[0.05, 0.1, 0.15],
    )

    job = service.enqueue(
        "demo_sleep",
        payload={"duration_s": 1, "fail": True, "fail_category": "transient"},
        max_attempts=3,
    )

    await runner.start()

    # Wait until all retries exhaust and job fails
    for _ in range(60):
        await asyncio.sleep(0.2)
        with Session(engine) as session:
            j = session.get(Job, job.id)
            if j and j.status == "failed":
                assert j.attempts == 3
                assert j.error_category == "transient"
                break
    else:
        pytest.fail("Job did not fail after exhausting retries")

    await runner.stop()


def test_idempotent_enqueue(test_db):
    engine, _ = test_db
    service = JobService(engine=engine)

    # First enqueue
    job1 = service.enqueue("demo_sleep", payload={"foo": "bar"}, input_hash="hash_abc_123")
    assert job1.status == "queued"

    # Simulate success
    with Session(engine) as session:
        j = session.get(Job, job1.id)
        j.status = "succeeded"
        session.add(j)
        session.commit()

    # Second enqueue with same hash & type
    job2 = service.enqueue("demo_sleep", payload={"foo": "bar"}, input_hash="hash_abc_123")
    assert job2.id == job1.id

    # Verify only 1 record exists in DB
    with Session(engine) as session:
        jobs = session.exec(select(Job).where(Job.input_hash == "hash_abc_123")).all()
        assert len(jobs) == 1


def test_restart_recovery(test_db):
    engine, data_dir = test_db
    # Create a job in 'running' state directly in DB
    with Session(engine) as session:
        job = Job(
            id="J_RESTART_TEST",
            type="demo_sleep",
            status="running",
            attempts=1,
            progress=0.5,
        )
        session.add(job)
        session.commit()

    # Instantiate a new runner and call recover_running_jobs
    new_runner = JobRunner(engine=engine, data_dir=data_dir)
    new_runner.recover_running_jobs()

    with Session(engine) as session:
        recovered = session.get(Job, "J_RESTART_TEST")
        assert recovered is not None
        assert recovered.status == "queued"
        # attempts must be preserved
        assert recovered.attempts == 1
