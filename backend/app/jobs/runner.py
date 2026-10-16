import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
import uuid

from sqlalchemy import Engine
from sqlmodel import Session, select

from app.config import settings
from app.db import engine as global_engine
from app.errors import AppError
from app.jobs.event_bus import event_bus
from app.jobs.registry import JobError, _check_payload, get_handler, is_async_handler
from app.models.job import Job
from app.schemas.job import JobRead

logger = logging.getLogger(__name__)


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

        # Reject secret-like payload keys (SPEC §5.6)
        _check_payload(payload)

        with Session(self.engine) as session:
            # Idempotency: reuse an already-succeeded job with the same hash
            if input_hash:
                existing = session.exec(
                    select(Job).where(
                        Job.type == type,
                        Job.input_hash == input_hash,
                        Job.status == "succeeded",
                    )
                ).first()
                if existing:
                    return existing

            # B3: validate depends_on — fail immediately if parent doesn't exist
            for dep_id in depends_on:
                dep = session.get(Job, dep_id)
                if dep is None:
                    # Create the job directly as failed/permanent
                    job_id = f"J{uuid.uuid4().hex[:6].upper()}"
                    job = Job(
                        id=job_id,
                        type=type,
                        status="failed",
                        depends_on=depends_on,
                        input_hash=input_hash,
                        attempts=0,
                        max_attempts=max_attempts,
                        progress=0.0,
                        log_path=f"jobs/{job_id}.log",
                        payload=payload,
                        error_category="permanent",
                        error_message=f"Phụ thuộc vào job không tồn tại: {dep_id}",
                        created_at=datetime.now(timezone.utc),
                        finished_at=datetime.now(timezone.utc),
                    )
                    session.add(job)
                    session.commit()
                    session.refresh(job)
                    self._emit_event(job)
                    return job

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

        self._emit_event(job)
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
            job.next_run_at = None
            job.started_at = None
            job.finished_at = None
            session.add(job)
            session.commit()
            session.refresh(job)

        self._emit_event(job)

        # B3: when a parent job is retried, clear user_action_required on children
        self._clear_children_notification(job_id)

        return job

    def _clear_children_notification(self, parent_id: str) -> None:
        """When parent job is retried, remove blocking notice from waiting children."""
        with Session(self.engine) as session:
            all_queued = session.exec(select(Job).where(Job.status == "queued")).all()
            for child in all_queued:
                if parent_id in (child.depends_on or []) and child.user_action_required:
                    child.user_action_required = None
                    session.add(child)
                    self._emit_event(child)
            session.commit()

    def cancel(self, job_id: str, runner: Optional["JobRunner"] = None) -> Job:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if not job:
                raise AppError("JOB_NOT_FOUND", "Không tìm thấy job", status_code=404)

            if job.status in ("succeeded", "failed", "cancelled"):
                return job

            if job.status in ("queued",):
                # B4: also catches jobs waiting in backoff (status=queued + next_run_at set)
                job.status = "cancelled"
                job.finished_at = datetime.now(timezone.utc)
                session.add(job)
                session.commit()
                session.refresh(job)
                self._emit_event(job)
            elif job.status == "running":
                # Signal the runner worker to stop; worker will handle status transition
                if runner:
                    runner.request_cancel(job_id)

        return job

    def _emit_event(self, job: Job) -> None:
        """Publish job.updated from any thread or async context (thread-safe)."""
        data = JobRead.model_validate(job).model_dump(mode="json")
        event_bus.publish_threadsafe("job.updated", data)


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
        """Reset jobs stuck in 'running' state back to 'queued' on startup."""
        with Session(self.engine) as session:
            running_jobs = session.exec(select(Job).where(Job.status == "running")).all()
            for job in running_jobs:
                job.status = "queued"
                job.next_run_at = None
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
                await self._update_blocked_children()
            except Exception:
                # N1: log exceptions from the worker loop instead of silently swallowing
                logger.exception("Unexpected error in job runner poll loop")
            await asyncio.sleep(0.5)

    async def _update_blocked_children(self) -> None:
        """B3: For queued children whose parent is failed/cancelled, set user_action_required."""
        with Session(self.engine) as session:
            queued_jobs = session.exec(select(Job).where(Job.status == "queued")).all()
            for child in queued_jobs:
                if not child.depends_on:
                    continue
                blocked_by: list[str] = []
                for dep_id in child.depends_on:
                    dep = session.get(Job, dep_id)
                    if dep and dep.status in ("failed", "cancelled"):
                        blocked_by.append(dep_id)

                if blocked_by:
                    msg = f"Chờ job {', '.join(blocked_by)} được sửa hoặc chạy lại"
                    if child.user_action_required != msg:
                        child.user_action_required = msg
                        session.add(child)
                        session.commit()
                        session.refresh(child)
                        self._emit_event(child)

    async def _poll_and_spawn(self) -> None:
        # Reap finished tasks
        finished_ids = [jid for jid, t in self._active_tasks.items() if t.done()]
        for jid in finished_ids:
            del self._active_tasks[jid]

        slots = self.concurrency - len(self._active_tasks)
        if slots <= 0:
            return

        now = datetime.now(timezone.utc)

        with Session(self.engine) as session:
            # B4: only pick up jobs whose next_run_at is due (or null)
            queued_jobs = session.exec(
                select(Job)
                .where(Job.status == "queued")
                .order_by(Job.created_at.asc())
            ).all()

            for job in queued_jobs:
                if slots <= 0:
                    break
                if job.id in self._active_tasks:
                    continue

                # B4: respect backoff schedule
                if job.next_run_at and job.next_run_at > now:
                    continue

                # Check dependencies
                deps_met = True
                if job.depends_on:
                    for dep_id in job.depends_on:
                        dep = session.get(Job, dep_id)
                        if not dep or dep.status != "succeeded":
                            deps_met = False
                            break

                if not deps_met:
                    continue

                task = asyncio.create_task(self._execute_job(job.id))
                self._active_tasks[job.id] = task
                slots -= 1

    async def _execute_job(self, job_id: str) -> None:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if not job or job.status != "queued":
                return

            job.status = "running"
            job.next_run_at = None
            job.started_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()
            session.refresh(job)

        self._emit_event(job)

        log_path = (
            self.data_dir / job.log_path
            if job.log_path
            else (self.data_dir / "jobs" / f"{job_id}.log")
        )

        # N4: throttle progress updates — max 4 per second, always flush last
        _last_progress_time: list[float] = [0.0]
        _THROTTLE_INTERVAL = 0.25  # 250ms = 4 updates/s max

        def progress_callback(prog: float, msg: Optional[str]) -> None:
            now_mono = time.monotonic()
            elapsed = now_mono - _last_progress_time[0]
            if elapsed < _THROTTLE_INTERVAL and prog < 1.0:
                return
            _last_progress_time[0] = now_mono
            with Session(self.engine) as s:
                j = s.get(Job, job_id)
                if j and j.status == "running":
                    j.progress = prog
                    s.add(j)
                    s.commit()
                    s.refresh(j)
                    self._emit_event(j)

        from app.jobs.registry import JobContext

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
                    self._emit_event(j)
            self._cancel_flags.pop(job_id, None)
            return

        try:
            # B2: dispatch sync handlers via asyncio.to_thread so they don't block the loop
            if is_async_handler(handler):
                await handler(ctx)
            else:
                await asyncio.to_thread(handler, ctx)

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
                    self._emit_event(j)

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
                            # B4: set status=queued + next_run_at instead of holding slot
                            j.status = "queued"
                            j.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                            session.add(j)
                            session.commit()
                            session.refresh(j)
                            self._emit_event(j)
                        else:
                            j.status = "failed"
                            j.finished_at = datetime.now(timezone.utc)
                            session.add(j)
                            session.commit()
                            session.refresh(j)
                            self._emit_event(j)
                    else:
                        j.status = "failed"
                        j.finished_at = datetime.now(timezone.utc)
                        session.add(j)
                        session.commit()
                        session.refresh(j)
                        self._emit_event(j)

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
                    self._emit_event(j)

        finally:
            self._cancel_flags.pop(job_id, None)

    def _emit_event(self, job: Job) -> None:
        """Thread-safe event emission (works from both async context and thread workers)."""
        data = JobRead.model_validate(job).model_dump(mode="json")
        event_bus.publish_threadsafe("job.updated", data)


# Global instances
job_service = JobService()
job_runner = JobRunner()
