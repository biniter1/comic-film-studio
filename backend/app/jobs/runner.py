import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.config import settings
from app.db import engine as global_engine
from app.errors import AppError
from app.jobs.event_bus import event_bus
from app.jobs.registry import JobContext, JobError, get_handler
from app.models.job import Job
from app.schemas.job import JobRead


class JobService:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or global_engine

    def enqueue(
        self,
        type: str,
        payload: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
        input_hash: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Job:
        payload = payload or {}
        depends_on = depends_on or []

        with Session(self.engine) as session:
            # Idempotency check: if input_hash matches a succeeded job of same type, reuse it
            if input_hash:
                statement = select(Job).where(
                    Job.type == type,
                    Job.input_hash == input_hash,
                    Job.status == "succeeded",
                )
                existing = session.exec(statement).first()
                if existing:
                    return existing

            job_id = f"J{uuid.uuid4().hex[:6].upper()}"
            job = Job(
                id=job_id,
                type=type,
                status="queued",
                depends_on=depends_on,
                input_hash=input_hash,
                attempts=0,
                max_attempts=max_attempts,
                progress=0.0,
                log_path=f"jobs/{job_id}.log",
                payload=payload,
                created_at=datetime.now(timezone.utc),
            )
            session.add(job)
            session.commit()
            session.refresh(job)

        self._publish_job_updated(job)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with Session(self.engine) as session:
            return session.get(Job, job_id)

    def list_jobs(self, status: Optional[str] = None) -> list[Job]:
        with Session(self.engine) as session:
            query = select(Job)
            if status:
                query = query.where(Job.status == status)
            query = query.order_by(Job.created_at.desc())
            return list(session.exec(query).all())

    def retry(self, job_id: str) -> Job:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if not job:
                raise AppError("JOB_NOT_FOUND", "Không tìm thấy job", status_code=404)

            if job.status not in ("failed", "cancelled"):
                raise AppError(
                    "JOB_NOT_RETRYABLE",
                    f"Chỉ có thể chạy lại job bị lỗi hoặc bị hủy (hiện tại: {job.status})",
                    status_code=409,
                )

            job.status = "queued"
            job.attempts = 0
            job.progress = 0.0
            job.error_category = None
            job.error_message = None
            job.user_action_required = None
            job.started_at = None
            job.finished_at = None
            session.add(job)
            session.commit()
            session.refresh(job)

        self._publish_job_updated(job)
        return job

    def cancel(self, job_id: str, runner: Optional["JobRunner"] = None) -> Job:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if not job:
                raise AppError("JOB_NOT_FOUND", "Không tìm thấy job", status_code=404)

            if job.status in ("succeeded", "failed", "cancelled"):
                return job

            if job.status == "queued":
                job.status = "cancelled"
                job.finished_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()
                session.refresh(job)
            elif job.status == "running":
                if runner:
                    runner.request_cancel(job_id)
                # Keep running status until worker exits or mark cancel flag
                return job

        self._publish_job_updated(job)
        return job

    def _publish_job_updated(self, job: Job) -> None:
        try:
            loop = asyncio.get_running_loop()
            data = JobRead.model_validate(job).model_dump(mode="json")
            loop.create_task(event_bus.publish("job.updated", data))
        except RuntimeError:
            pass


class JobRunner:
    def __init__(
        self,
        engine: Engine | None = None,
        concurrency: int | None = None,
        data_dir: Path | None = None,
        backoff_delays: list[float] | None = None,
    ) -> None:
        self.engine = engine or global_engine
        self.concurrency = concurrency or settings.job_concurrency
        self.data_dir = data_dir or settings.data_dir
        self.backoff_delays = backoff_delays if backoff_delays is not None else [2.0, 8.0, 30.0]
        self._running = False
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._active_tasks: dict[str, asyncio.Task[None]] = {}
        self._cancel_flags: dict[str, bool] = {}

    def recover_running_jobs(self) -> None:
        """Reset jobs in 'running' status back to 'queued' on startup (preserving attempts)."""
        with Session(self.engine) as session:
            running_jobs = session.exec(select(Job).where(Job.status == "running")).all()
            for job in running_jobs:
                job.status = "queued"
                session.add(job)
            session.commit()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.recover_running_jobs()
        self._worker_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        # Wait for active tasks
        for task in list(self._active_tasks.values()):
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)
            self._active_tasks.clear()

    def request_cancel(self, job_id: str) -> None:
        self._cancel_flags[job_id] = True

    def is_cancelled(self, job_id: str) -> bool:
        return self._cancel_flags.get(job_id, False)

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._poll_and_spawn()
            except Exception:
                pass
            await asyncio.sleep(0.5)

    async def _poll_and_spawn(self) -> None:
        # Clean finished active tasks
        finished_ids = [jid for jid, t in self._active_tasks.items() if t.done()]
        for jid in finished_ids:
            del self._active_tasks[jid]

        slots = self.concurrency - len(self._active_tasks)
        if slots <= 0:
            return

        with Session(self.engine) as session:
            # Query queued jobs
            queued_jobs = session.exec(
                select(Job).where(Job.status == "queued").order_by(Job.created_at.asc())
            ).all()

            for job in queued_jobs:
                if slots <= 0:
                    break
                if job.id in self._active_tasks:
                    continue

                # Check dependencies
                deps_met = True
                if job.depends_on:
                    for dep_id in job.depends_on:
                        dep_job = session.get(Job, dep_id)
                        if not dep_job or dep_job.status != "succeeded":
                            deps_met = False
                            break

                if not deps_met:
                    continue

                # Spawn execution
                task = asyncio.create_task(self._execute_job(job.id))
                self._active_tasks[job.id] = task
                slots -= 1

    async def _execute_job(self, job_id: str) -> None:
        # Step 1: Mark job as running
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if not job:
                return
            if job.status != "queued":
                return

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()
            session.refresh(job)

        self._emit_job_event(job)

        log_path = (
            self.data_dir / job.log_path
            if job.log_path
            else (self.data_dir / "jobs" / f"{job_id}.log")
        )

        def progress_callback(prog: float, msg: Optional[str]) -> None:
            with Session(self.engine) as s:
                j = s.get(Job, job_id)
                if j and j.status == "running":
                    j.progress = prog
                    s.add(j)
                    s.commit()
                    s.refresh(j)
                    self._emit_job_event(j)

        ctx = JobContext(
            job_id=job.id,
            payload=job.payload or {},
            log_file=log_path,
            progress_callback=progress_callback,
            cancel_check=lambda: self.is_cancelled(job_id),
        )

        handler = get_handler(job.type)
        if not handler:
            ctx.log(f"Lỗi: Không tìm thấy handler cho loại job '{job.type}'")
            with Session(self.engine) as session:
                j = session.get(Job, job_id)
                if j:
                    j.status = "failed"
                    j.error_category = "permanent"
                    j.error_message = f"Không tìm thấy handler cho loại job '{job.type}'"
                    j.finished_at = datetime.now(timezone.utc)
                    session.add(j)
                    session.commit()
                    session.refresh(j)
                    self._emit_job_event(j)
            self._cancel_flags.pop(job_id, None)
            return

        try:
            await handler(ctx)

            with Session(self.engine) as session:
                j = session.get(Job, job_id)
                if j:
                    if self.is_cancelled(job_id):
                        j.status = "cancelled"
                    else:
                        j.status = "succeeded"
                        j.progress = 1.0
                    j.finished_at = datetime.now(timezone.utc)
                    session.add(j)
                    session.commit()
                    session.refresh(j)
                    self._emit_job_event(j)

        except JobError as je:
            ctx.log(f"JobError ({je.category}): {je.message}")
            with Session(self.engine) as session:
                j = session.get(Job, job_id)
                if j:
                    j.error_category = je.category
                    j.error_message = je.message
                    j.user_action_required = je.user_action_required

                    if je.category == "transient":
                        j.attempts += 1
                        if j.attempts < j.max_attempts:
                            delay_idx = min(j.attempts - 1, len(self.backoff_delays) - 1)
                            delay = self.backoff_delays[delay_idx]
                            ctx.log(f"Retry lần {j.attempts}/{j.max_attempts} sau {delay}s...")
                            # Backoff delay then re-queue
                            session.add(j)
                            session.commit()
                            session.refresh(j)
                            self._emit_job_event(j)

                            # Handle backoff delay
                            await asyncio.sleep(delay)
                            with Session(self.engine) as session_retry:
                                j_retry = session_retry.get(Job, job_id)
                                if j_retry and j_retry.status == "running":
                                    j_retry.status = "queued"
                                    session_retry.add(j_retry)
                                    session_retry.commit()
                                    session_retry.refresh(j_retry)
                                    self._emit_job_event(j_retry)
                            return
                        else:
                            j.status = "failed"
                            j.finished_at = datetime.now(timezone.utc)
                    else:
                        j.status = "failed"
                        j.finished_at = datetime.now(timezone.utc)

                    session.add(j)
                    session.commit()
                    session.refresh(j)
                    self._emit_job_event(j)

        except Exception as e:
            ctx.log(f"Lỗi không mong muốn: {str(e)}")
            with Session(self.engine) as session:
                j = session.get(Job, job_id)
                if j:
                    j.status = "failed"
                    j.error_category = "permanent"
                    j.error_message = str(e)
                    j.finished_at = datetime.now(timezone.utc)
                    session.add(j)
                    session.commit()
                    session.refresh(j)
                    self._emit_job_event(j)

        finally:
            self._cancel_flags.pop(job_id, None)

    def _emit_job_event(self, job: Job) -> None:
        try:
            loop = asyncio.get_running_loop()
            data = JobRead.model_validate(job).model_dump(mode="json")
            loop.create_task(event_bus.publish("job.updated", data))
        except RuntimeError:
            pass


# Global job service & runner instances
job_service = JobService()
job_runner = JobRunner()
