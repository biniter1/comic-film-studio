"""Pydantic contracts for AI outputs (SPEC §5.1, §4.5). Validation failures are fed back to the
model (see engine.py), so error messages here should be explicit."""

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FrameType = Literal["scene", "dialogue_only", "caption", "sfx_only", "credit"]
TextKind = Literal["dialogue", "inner_thought", "narration", "technique_name", "sfx", "system"]
Gender = Literal["male", "female", "unknown"]
Age = Literal["child", "teen", "young_adult", "middle_aged", "elderly", "unknown"]
BelongsTo = Literal["self", "prev", "next"]
TermKind = Literal["person", "place", "technique", "realm", "sect", "item", "title", "other"]
Role = Literal["main", "supporting", "extra"]
HeightClass = Literal["child", "short", "average", "tall", "giant"]


def _clean_enum_str(v: Any) -> Any:
    if v is None:
        return None
    if not isinstance(v, str):
        return v
    s = v.strip().lower()
    return re.sub(r"[\s\-]+", "_", s)


def normalize_gender(v: Any) -> Any:
    if v is None or (isinstance(v, str) and not v.strip()):
        return "unknown"
    return _clean_enum_str(v)


def normalize_age(v: Any) -> Any:
    if v is None or (isinstance(v, str) and not v.strip()):
        return "unknown"
    s = _clean_enum_str(v)
    synonyms = {
        "adult": "young_adult",
        "young_adult": "young_adult",
        "middle_age": "middle_aged",
        "middle_aged": "middle_aged",
        "old": "elderly",
        "elder": "elderly",
        "elderly": "elderly",
        "kid": "child",
        "child": "child",
    }
    return synonyms.get(s, s)


def normalize_text_kind(v: Any) -> Any:
    s = _clean_enum_str(v)
    if not s:
        return v
    synonyms = {
        "narrator": "narration",
        "caption": "narration",
        "thought": "inner_thought",
    }
    return synonyms.get(s, s)


def normalize_belongs_to(v: Any) -> Any:
    s = _clean_enum_str(v)
    if not s:
        return v
    synonyms = {
        "previous": "prev",
    }
    return synonyms.get(s, s)


def normalize_frame_type(v: Any) -> Any:
    return _clean_enum_str(v)


def normalize_term_kind(v: Any) -> Any:
    s = _clean_enum_str(v)
    if not s:
        return "other"
    return s


def normalize_role(v: Any) -> Any:
    if v is None or (isinstance(v, str) and not v.strip()):
        return "supporting"
    s = _clean_enum_str(v)
    synonyms = {
        "chinh": "main",
        "primary": "main",
        "protagonist": "main",
        "phu": "supporting",
        "secondary": "supporting",
        "quan_chung": "extra",
        "background": "extra",
        "crowd": "extra",
    }
    return synonyms.get(s, s)


def normalize_bool(v: Any) -> bool:
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes", "t"):
            return True
        if s in ("false", "0", "no", "f"):
            return False
    return bool(v)


def normalize_height_class(v: Any) -> Any:
    if v is None or (isinstance(v, str) and not v.strip()):
        return "average"
    s = _clean_enum_str(v)
    synonyms = {
        "medium": "average",
        "normal": "average",
        "tall": "tall",
        "short": "short",
        "child": "child",
        "giant": "giant",
        "huge": "giant",
    }
    return synonyms.get(s, s)


class ReadText(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: int = Field(ge=1)
    kind: TextKind
    text: str = Field(min_length=1)
    speaker_key: Optional[str] = None
    speaker_label: Optional[str] = None
    speaker_gender: Gender = "unknown"
    speaker_age: Age = "unknown"
    speaker_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    belongs_to: BelongsTo = "self"

    @model_validator(mode="before")
    @classmethod
    def _handle_speaker_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            if "speaker" in data:
                spk = data.pop("speaker")
                if spk is not None:
                    spk_str = str(spk).strip()
                    if spk_str:
                        has_key = bool(data.get("speaker_key"))
                        has_label = bool(data.get("speaker_label"))
                        if not has_key and not has_label:
                            if re.match(r"^[a-z0-9_]+$", spk_str):
                                data["speaker_key"] = spk_str
                            else:
                                data["speaker_label"] = spk_str
        return data

    @field_validator("kind", mode="before")
    @classmethod
    def _validate_kind(cls, v: Any) -> Any:
        return normalize_text_kind(v)

    @field_validator("speaker_gender", mode="before")
    @classmethod
    def _validate_gender(cls, v: Any) -> Any:
        return normalize_gender(v)

    @field_validator("speaker_age", mode="before")
    @classmethod
    def _validate_age(cls, v: Any) -> Any:
        return normalize_age(v)

    @field_validator("belongs_to", mode="before")
    @classmethod
    def _validate_belongs_to(cls, v: Any) -> Any:
        return normalize_belongs_to(v)


class FrameReadingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_id: str
    frame_type: FrameType
    description: str = ""
    characters: list[str] = []
    texts: list[ReadText] = []
    intensity: int = Field(default=2, ge=1, le=5)
    continues_previous: bool = False
    technique_hint: Optional[str] = None
    implied_motion: Optional[str] = None

    @field_validator("frame_type", mode="before")
    @classmethod
    def _validate_frame_type(cls, v: Any) -> Any:
        return normalize_frame_type(v)

    @field_validator("texts")
    @classmethod
    def _line_numbers_unique(cls, v: list[ReadText]) -> list[ReadText]:
        nos = [t.line_no for t in v]
        if len(nos) != len(set(nos)):
            raise ValueError("line_no must be unique within a frame")
        return sorted(v, key=lambda t: t.line_no)


class NewCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    aliases: list[str] = []
    gender: Gender = "unknown"
    age_group: Age = "unknown"
    voice_style: Optional[str] = None
    role: Role = "supporting"
    is_group: bool = False
    group_size_hint: Optional[str] = None

    @field_validator("gender", mode="before")
    @classmethod
    def _validate_gender(cls, v: Any) -> Any:
        return normalize_gender(v)

    @field_validator("age_group", mode="before")
    @classmethod
    def _validate_age(cls, v: Any) -> Any:
        return normalize_age(v)

    @field_validator("role", mode="before")
    @classmethod
    def _validate_role(cls, v: Any) -> Any:
        return normalize_role(v)

    @field_validator("is_group", mode="before")
    @classmethod
    def _validate_is_group(cls, v: Any) -> Any:
        return normalize_bool(v)


class LookProfileOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    look_lock: str = Field(min_length=1)
    outfit_lock: str = Field(min_length=1)
    short_id: str = Field(min_length=1)
    height_class: HeightClass = "average"
    palette: list[str] = Field(default_factory=list)
    distinctive: list[str] = Field(default_factory=list)

    @field_validator("height_class", mode="before")
    @classmethod
    def _validate_height_class(cls, v: Any) -> Any:
        return normalize_height_class(v)

    @field_validator("palette", mode="before")
    @classmethod
    def _validate_palette(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(x) for x in v][:5]

    @field_validator("distinctive", mode="before")
    @classmethod
    def _validate_distinctive(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(x) for x in v][:5]


class ReadBatchOut(BaseModel):
    frames: list[FrameReadingOut]
    new_characters: list[NewCharacter] = []
    running_summary: str = ""


class SpeakerSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker_key: Optional[str] = None
    speaker_label: Optional[str] = None
    reason: str = Field(..., max_length=200)


class DialogueEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: str
    text: str = Field(min_length=1)
    edit_note: Optional[str] = None
    uncertain: bool = False
    speaker_suggestion: Optional[SpeakerSuggestion] = None


class GlossaryCandidate(BaseModel):
    term: str = Field(min_length=1)
    kind: TermKind = "other"
    variants: list[str] = []
    note: Optional[str] = None

    @field_validator("kind", mode="before")
    @classmethod
    def _validate_term_kind(cls, v: Any) -> Any:
        return normalize_term_kind(v)


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


# ---------------------------------------------------------------------------
# Phase 2c: plan (scenes) + shots (storyboard) — SPEC §4.6, §5.3
# ---------------------------------------------------------------------------
ShotSize = Literal[
    "extreme_wide",
    "wide",
    "full",
    "medium",
    "medium_close_up",
    "close_up",
    "extreme_close_up",
    "insert",
]
Movement = Literal[
    "static",
    "push_in",
    "pull_out",
    "pan_left",
    "pan_right",
    "tilt_up",
    "tilt_down",
    "truck_left",
    "truck_right",
    "orbit_left",
    "orbit_right",
    "follow",
    "crane_up",
    "crane_down",
    "handheld_shake",
    "crash_zoom",
]
Speed = Literal["slow", "medium", "fast"]
Angle = Literal["eye", "low", "high", "overhead", "dutch"]
Transition = Literal["cut", "continuous", "match"]
ScreenPos = Literal["left", "center", "right"]
Depth = Literal["fg", "mg", "bg"]
Facing = Literal["left", "right", "camera", "away"]

_SYNONYMS = {
    "shot_size": {
        "ews": "extreme_wide",
        "ws": "wide",
        "long": "wide",
        "establishing": "extreme_wide",
        "ms": "medium",
        "mcu": "medium_close_up",
        "cu": "close_up",
        "closeup": "close_up",
        "ecu": "extreme_close_up",
        "extreme_closeup": "extreme_close_up",
        "detail": "insert",
        "full_shot": "full",
        "medium_shot": "medium",
        "wide_shot": "wide",
    },
    "movement": {
        "none": "static",
        "still": "static",
        "dolly_in": "push_in",
        "zoom_in": "push_in",
        "dolly_out": "pull_out",
        "zoom_out": "pull_out",
        "orbit": "orbit_right",
        "arc": "orbit_right",
        "tracking": "follow",
        "track": "follow",
        "shake": "handheld_shake",
        "handheld": "handheld_shake",
        "crane": "crane_up",
        "pan": "pan_right",
        "tilt": "tilt_up",
    },
    "angle": {
        "eye_level": "eye",
        "low_angle": "low",
        "high_angle": "high",
        "top_down": "overhead",
        "birds_eye": "overhead",
        "dutch_angle": "dutch",
    },
    "speed": {"normal": "medium", "moderate": "medium", "quick": "fast"},
    "transition_in": {"hard_cut": "cut", "continue": "continuous", "match_cut": "match"},
    "screen_pos": {"middle": "center", "centre": "center"},
    "depth": {"foreground": "fg", "midground": "mg", "middle": "mg", "background": "bg"},
    "facing": {"viewer": "camera", "front": "camera", "back": "away", "toward_camera": "camera"},
}


def _norm(field: str, v: Any) -> Any:
    s = _clean_enum_str(v)
    if not isinstance(s, str):
        return s
    return _SYNONYMS.get(field, {}).get(s, s)


class SceneDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    frame_ids: list[str] = Field(min_length=1)
    summary: str = ""
    location_key: Optional[str] = None
    mood: Optional[str] = None


class NewLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str = Field(pattern=r"^[a-z0-9_]+$")
    name_vi: str
    location_lock: Optional[str] = None


class PlanOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    scenes: list[SceneDraft] = Field(min_length=1)
    new_locations: list[NewLocation] = []


class CameraOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shot_size: ShotSize = "medium"
    movement: Movement = "static"
    speed: Speed = "slow"
    angle: Angle = "eye"

    @model_validator(mode="before")
    @classmethod
    def _loose(cls, v: Any) -> Any:
        if isinstance(v, dict):
            v = dict(v)
            for k in ("shot_size", "movement", "speed", "angle"):
                if v.get(k) is None:
                    v.pop(k, None)
                else:
                    v[k] = _norm(k, v[k])
            if isinstance(v.get("movement"), list):  # model listed several → keep the first
                v["movement"] = _norm("movement", v["movement"][0]) if v["movement"] else "static"
        return v


class BlockingOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    character_key: str
    outfit_key: Optional[str] = None
    screen_pos: ScreenPos = "center"
    depth: Depth = "mg"
    facing: Facing = "camera"
    pose: str = ""

    @model_validator(mode="before")
    @classmethod
    def _loose(cls, v: Any) -> Any:
        if isinstance(v, dict):
            v = dict(v)
            for k in ("screen_pos", "depth", "facing"):
                if v.get(k) is None:
                    v.pop(k, None)
                else:
                    v[k] = _norm(k, v[k])
        return v


class BeatOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    t0: float = Field(ge=0)
    t1: float = Field(gt=0)
    action: str = Field(min_length=1)


class ShotDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    frame_ids: list[str] = []
    inserted: bool = False
    transition_in: Transition = "cut"
    duration_s: float = Field(default=4.0, gt=0, le=15)
    camera: CameraOut = CameraOut()
    location_key: Optional[str] = None
    blocking: list[BlockingOut] = []
    beats: list[BeatOut] = []
    start_state: str = ""
    end_state: str = ""
    action: str = ""
    emotion: str = ""
    line_ids: list[str] = []
    sfx_notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _loose(cls, v: Any) -> Any:
        if isinstance(v, dict) and v.get("transition_in") is not None:
            v = dict(v)
            v["transition_in"] = _norm("transition_in", v["transition_in"])
        return v


class ShotsOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    shots: list[ShotDraft] = Field(min_length=1)
