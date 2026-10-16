from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default=None, primary_key=True)
    type: str = Field(index=True)
    status: str = Field(
        default="queued", index=True
    )  # queued|running|waiting_user|succeeded|failed|cancelled
    depends_on: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    input_hash: Optional[str] = Field(default=None, index=True)
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=3)
    progress: float = Field(default=0.0)
    log_path: Optional[str] = Field(default=None)
    error_category: Optional[str] = Field(default=None)  # transient|invalid_output|permanent|quota
    error_message: Optional[str] = Field(default=None)
    user_action_required: Optional[str] = Field(default=None)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # B4: backoff without holding concurrency slot
    next_run_at: Optional[datetime] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
