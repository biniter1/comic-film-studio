"""Phase 1 domain tables (SPEC §3.1, §5.4)."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(default_factory=lambda: new_id("PJ"), primary_key=True)
    name: str
    settings_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Chapter(SQLModel, table=True):
    __tablename__ = "chapters"

    id: str = Field(default_factory=lambda: new_id("CH"), primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    title: str
    source_url: Optional[str] = None
    # empty | imported | frames_draft | frames_approved
    status: str = Field(default="empty", index=True)
    # Strip geometry (webtoon): common width all pages are scaled to
    strip_width: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Asset(SQLModel, table=True):
    __tablename__ = "assets"

    id: str = Field(default_factory=lambda: new_id("A"), primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    chapter_id: Optional[str] = Field(default=None, foreign_key="chapters.id", index=True)
    # page, page_preview, frame, ref, keyframe, boundary_raw, boundary_fixed, take, tts, export
    kind: str = Field(index=True)
    # Relative to the project directory, always with forward slashes
    path: str
    sha256: Optional[str] = None
    version: int = 1
    parent_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    shot_code: Optional[str] = None
    provider: Optional[str] = None
    prompt_snapshot: Optional[str] = None
    approval: str = "pending"  # pending | approved | rejected
    notes: Optional[str] = None
    media: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    missing: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class SourcePage(SQLModel, table=True):
    __tablename__ = "source_pages"

    id: str = Field(default_factory=lambda: new_id("SP"), primary_key=True)
    chapter_id: str = Field(foreign_key="chapters.id", index=True)
    idx: int
    asset_id: str = Field(foreign_key="assets.id")
    preview_asset_id: Optional[str] = Field(default=None, foreign_key="assets.id")
    original_name: str
    sha256: str
    width: int
    height: int
    status: str = "ok"  # ok | excluded
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Frame(SQLModel, table=True):
    __tablename__ = "frames"

    id: str = Field(default_factory=lambda: new_id("FR"), primary_key=True)
    chapter_id: str = Field(foreign_key="chapters.id", index=True)
    idx: int
    asset_id: str = Field(foreign_key="assets.id")
    # Coordinates on the stitched strip (pages scaled to Chapter.strip_width, stacked)
    x0: int = 0
    y0: int
    x1: int
    y1: int
    origin: str = "auto"  # auto | manual
