from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    status: str
    depends_on: list[str] = []
    input_hash: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3
    progress: float = 0.0
    log_path: Optional[str] = None
    error_category: Optional[str] = None
    error_message: Optional[str] = None
    user_action_required: Optional[str] = None
    next_run_at: Optional[datetime] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobCreate(BaseModel):
    type: str
    payload: dict[str, Any] = {}
    depends_on: list[str] = []
    input_hash: Optional[str] = None
    max_attempts: int = 3


class JobDemoRequest(BaseModel):
    duration_s: int = 5
    fail: bool = False
    fail_category: Optional[str] = None
