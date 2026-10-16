from typing import Literal, Optional

from fastapi import APIRouter, Response

from app.config import settings
from app.errors import AppError
from app.jobs.runner import job_runner, job_service
from app.schemas.job import JobDemoRequest, JobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRead])
def list_jobs(status: Optional[str] = None) -> list[JobRead]:
    jobs = job_service.list_jobs(status=status)
    return [JobRead.model_validate(j) for j in jobs]


@router.post("/demo", response_model=JobRead)
def create_demo_job(
    request: JobDemoRequest = JobDemoRequest(),
    job_type: Literal["demo_sleep", "demo_cpu"] = "demo_sleep",
) -> JobRead:
    """Create a demo job. Use job_type=demo_cpu to test the sync (CPU-bound) handler."""
    job = job_service.enqueue(
        type=job_type,
        payload=request.model_dump(),
        max_attempts=3,
    )
    return JobRead.model_validate(job)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str) -> JobRead:
    job = job_service.get_job(job_id)
    if not job:
        raise AppError("JOB_NOT_FOUND", f"Không tìm thấy job với ID: {job_id}", status_code=404)
    return JobRead.model_validate(job)


@router.post("/{job_id}/retry", response_model=JobRead)
def retry_job(job_id: str) -> JobRead:
    job = job_service.retry(job_id)
    return JobRead.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: str) -> JobRead:
    job = job_service.cancel(job_id, runner=job_runner)
    return JobRead.model_validate(job)


@router.get("/{job_id}/log")
def get_job_log(job_id: str) -> Response:
    job = job_service.get_job(job_id)
    if not job:
        raise AppError("JOB_NOT_FOUND", f"Không tìm thấy job với ID: {job_id}", status_code=404)

    log_path = (
        settings.data_dir / job.log_path
        if job.log_path
        else (settings.data_dir / "jobs" / f"{job_id}.log")
    )
    if not log_path.exists():
        return Response(content="", media_type="text/plain; charset=utf-8")

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        return Response(content=content, media_type="text/plain; charset=utf-8")
    except Exception as e:
        raise AppError("LOG_READ_FAILED", f"Không thể đọc file log: {str(e)}", status_code=500)
