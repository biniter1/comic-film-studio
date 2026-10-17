"""Phase 2c: scenes and shots with storyboard fields (SPEC §3.1, §4.6, §5.3)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.project import new_id, utcnow


class Scene(SQLModel, table=True):
    __tablename__ = "scenes"

    id: str = Field(default_factory=lambda: new_id("SC"), primary_key=True)
    chapter_id: str = Field(foreign_key="chapters.id", index=True)
    code: str  # SC01
    order: int
    summary: str = ""
    frame_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    location_key: Optional[str] = None
    mood: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Shot(SQLModel, table=True):
    __tablename__ = "shots"

    id: str = Field(default_factory=lambda: new_id("SH"), primary_key=True)
    chapter_id: str = Field(foreign_key="chapters.id", index=True)
    scene_id: str = Field(foreign_key="scenes.id", index=True)
    code: str  # SH001
    order: int
    chain_code: str = ""  # C01
    chain_pos: int = 1
    transition_in: str = "cut"  # cut | continuous | match
    frame_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    duration_s: float = 4.0
    camera: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    location_key: Optional[str] = None
    blocking: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    beats: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    start_state: str = ""
    end_state: str = ""
    action: str = ""
    emotion: str = ""
    line_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    titles: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    sfx_notes: str = ""
    inserted: bool = False  # reaction shot suggested by AI, not drawn in the comic
    keyframe_prompt: str = ""
    video_prompt: str = ""
    attachments: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    prompt_override: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    rule_notes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    edited_by: str = "ai"  # ai | user
    state: str = "planned"
    is_stale: bool = False
    created_at: datetime = Field(default_factory=utcnow)
