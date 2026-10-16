"""Pydantic contracts for AI outputs (SPEC §5.1, §4.5). Validation failures are fed back to the
model (see engine.py), so error messages here should be explicit."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

FrameType = Literal["scene", "dialogue_only", "caption", "sfx_only", "credit"]
TextKind = Literal["dialogue", "inner_thought", "narration", "technique_name", "sfx", "system"]
Gender = Literal["male", "female", "unknown"]
Age = Literal["child", "teen", "young_adult", "middle_aged", "elderly", "unknown"]
BelongsTo = Literal["self", "prev", "next"]
TermKind = Literal["person", "place", "technique", "realm", "sect", "item", "title", "other"]


class ReadText(BaseModel):
    line_no: int = Field(ge=1)
    kind: TextKind
    text: str = Field(min_length=1)
    speaker_key: Optional[str] = None
    speaker_label: Optional[str] = None
    speaker_gender: Gender = "unknown"
    speaker_age: Age = "unknown"
    speaker_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    belongs_to: BelongsTo = "self"


class FrameReadingOut(BaseModel):
    frame_id: str
    frame_type: FrameType
    description: str = ""
    characters: list[str] = []
    texts: list[ReadText] = []
    intensity: int = Field(default=2, ge=1, le=5)
    continues_previous: bool = False
    technique_hint: Optional[str] = None
    implied_motion: Optional[str] = None

    @field_validator("texts")
    @classmethod
    def _line_numbers_unique(cls, v: list[ReadText]) -> list[ReadText]:
        nos = [t.line_no for t in v]
        if len(nos) != len(set(nos)):
            raise ValueError("line_no must be unique within a frame")
        return sorted(v, key=lambda t: t.line_no)


class NewCharacter(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    aliases: list[str] = []
    gender: Gender = "unknown"
    age_group: Age = "unknown"
    voice_style: Optional[str] = None


class ReadBatchOut(BaseModel):
    frames: list[FrameReadingOut]
    new_characters: list[NewCharacter] = []
    running_summary: str = ""


class DialogueEdit(BaseModel):
    line_id: str
    text: str = Field(min_length=1)
    edit_note: Optional[str] = None


class GlossaryCandidate(BaseModel):
    term: str = Field(min_length=1)
    kind: TermKind = "other"
    variants: list[str] = []
    note: Optional[str] = None


class AddressCandidate(BaseModel):
    speaker_key: str
    listener_key: str
    self_term: str
    address_term: str
    note: Optional[str] = None


class DialogueOut(BaseModel):
    lines: list[DialogueEdit]
    glossary_candidates: list[GlossaryCandidate] = []
    address_candidates: list[AddressCandidate] = []
