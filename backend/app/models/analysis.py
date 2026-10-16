"""Phase 2a tables: characters, dialogue, glossary, address rules, analysis runs (SPEC §4.5)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.project import new_id, utcnow


class Character(SQLModel, table=True):
    __tablename__ = "characters"

    id: str = Field(default_factory=lambda: new_id("CR"), primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    key: str = Field(index=True)  # snake_case, unique per project
    name: str
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    gender: str = "unknown"  # male | female | unknown
    age_group: str = "unknown"  # child | teen | young_adult | middle_aged | elderly | unknown
    voice_style: Optional[str] = None
    look_lock: Optional[str] = None
    voice_id: Optional[str] = None
    status: str = "suggested"  # suggested | approved
    height_class: str = "average"  # child | short | average | tall | giant
    ref_frame_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    look_status: str = "draft"  # draft | approved
    created_at: datetime = Field(default_factory=utcnow)


class CharacterOutfit(SQLModel, table=True):
    __tablename__ = "character_outfits"

    id: str = Field(default_factory=lambda: new_id("CO"), primary_key=True)
    character_id: str = Field(foreign_key="characters.id", index=True)
    key: str = Field(index=True)  # snake_case, unique per character
    name_vi: str
    outfit_lock: Optional[str] = None  # EN description
    short_id: Optional[str] = None  # EN 3-6 words
    is_default: bool = False
    sheet_asset_id: Optional[str] = Field(default=None, foreign_key="assets.id")
    sheet_status: str = "missing"  # missing | pending | approved
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Location(SQLModel, table=True):
    __tablename__ = "locations"

    id: str = Field(default_factory=lambda: new_id("LC"), primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    key: str = Field(index=True)  # snake_case, unique per project
    name_vi: str
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    location_lock: Optional[str] = None  # EN description
    ref_frame_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    sheet_asset_id: Optional[str] = Field(default=None, foreign_key="assets.id")
    sheet_status: str = "missing"  # missing | pending | approved
    created_at: datetime = Field(default_factory=utcnow)


class DialogueLine(SQLModel, table=True):
    __tablename__ = "dialogue_lines"

    id: str = Field(default_factory=lambda: new_id("DL"), primary_key=True)
    chapter_id: str = Field(foreign_key="chapters.id", index=True)
    order: int = Field(index=True)
    source_frame_id: str = Field(foreign_key="frames.id")
    anchor_frame_id: Optional[str] = Field(default=None, foreign_key="frames.id")
    belongs_to: str = "self"  # self | prev | next (AI hint used to compute the anchor)
    anchor_locked: bool = False  # user picked the anchor → never recomputed
    line_no: int = 1
    # dialogue | inner_thought | narration | technique_name | sfx | system
    kind: str = "dialogue"
    speaker_key: Optional[str] = None
    speaker_label: Optional[str] = None
    speaker_gender: str = "unknown"
    speaker_age: str = "unknown"
    speaker_confidence: float = 0.5
    text_raw: str
    text: str
    edited_by: str = "none"  # none | ai | user
    edit_note: Optional[str] = None
    needs_review: bool = False
    reviewed: bool = False
    shot_code: Optional[str] = None
    at_s: Optional[float] = None
    dur_s: Optional[float] = None


class GlossaryTerm(SQLModel, table=True):
    __tablename__ = "glossary_terms"

    id: str = Field(default_factory=lambda: new_id("GT"), primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    term: str
    # person | place | technique | realm | sect | item | title | other
    kind: str = "other"
    variants: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    note: Optional[str] = None
    status: str = "suggested"  # suggested | approved | rejected
    first_seen_chapter_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class AddressRule(SQLModel, table=True):
    __tablename__ = "address_rules"

    id: str = Field(default_factory=lambda: new_id("AR"), primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    speaker_key: str
    listener_key: str
    self_term: str
    address_term: str
    note: Optional[str] = None
    status: str = "suggested"  # suggested | approved | rejected


class AnalysisRun(SQLModel, table=True):
    """One unit of AI work (a batch of frames for `read`, a chunk of lines for `dialogue`)."""

    __tablename__ = "analysis_runs"

    id: str = Field(default_factory=lambda: new_id("AN"), primary_key=True)
    chapter_id: str = Field(foreign_key="chapters.id", index=True)
    stage: str  # read | dialogue
    unit_index: int = 0
    mode: str = "api"  # api | manual
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_version: str = "v1"
    input_hash: Optional[str] = Field(default=None, index=True)
    # pending | awaiting_paste | succeeded | failed
    status: str = "pending"
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    raw_output_path: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
