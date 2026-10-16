"""Data model cho toàn bộ pipeline.

Mọi quyết định của "đạo diễn" (LLM) đều được lưu thành JSON theo schema này,
để các bước sau (tạo ảnh, tạo video, dựng phim, QA) đọc lại cùng một kế hoạch.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Chữ trong truyện: phân loại để biết hiển thị kiểu gì
# ---------------------------------------------------------------------------
class TextKind(str, Enum):
    dialogue = "dialogue"              # lời thoại trong bong bóng -> TTS + phụ đề dưới
    inner_thought = "inner_thought"    # suy nghĩ -> TTS giọng nhỏ/echo + phụ đề nghiêng
    narration = "narration"            # khung dẫn truyện -> giọng kể + phụ đề trên
    technique_name = "technique_name"  # TÊN CHIÊU THỨC -> title card lớn trên màn hình
    sfx = "sfx"                        # chữ tượng thanh (ẦM! VÙ!) -> âm thanh + chữ động
    system = "system"                  # bảng hệ thống/level/thông báo -> khung UI


class TextElement(BaseModel):
    kind: TextKind
    text: str
    speaker: Optional[str] = None      # id nhân vật nếu biết
    panel_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Panel đầu vào
# ---------------------------------------------------------------------------
class Panel(BaseModel):
    id: str                            # "P001"
    page: str                          # tên file trang gốc
    path: str                          # đường dẫn ảnh panel đã cắt
    bbox: tuple[int, int, int, int]    # x, y, w, h trên trang gốc
    width: int
    height: int


class PanelReading(BaseModel):
    """Kết quả đọc 1 panel (Pass A)."""
    panel_id: str
    description: str
    characters: list[str] = []
    texts: list[TextElement] = []
    intensity: int = Field(1, ge=1, le=5)          # 1 = tĩnh, 5 = bùng nổ
    continues_previous: bool = False               # cùng khoảnh khắc/chiêu với panel trước
    technique_hint: Optional[str] = None           # tên chiêu nếu panel thuộc 1 chiêu thức
    implied_motion: Optional[str] = None           # chuyển động người đọc phải tưởng tượng


# ---------------------------------------------------------------------------
# Bible: khóa nhân vật + chiêu thức xuyên suốt cả bộ truyện
# ---------------------------------------------------------------------------
class Character(BaseModel):
    id: str
    name: str
    look_lock: str                     # mô tả ngoại hình tiếng Anh, chèn nguyên văn vào prompt
    ref_images: list[str] = []         # ảnh chuẩn (keyframe đẹp nhất) để đính kèm
    voice: Optional[str] = None        # id giọng TTS


class Technique(BaseModel):
    id: str
    name: str                          # tên hiển thị: "Ma La Lục Thức Thông"
    owner: Optional[str] = None
    element: Optional[str] = None      # lôi, hỏa, thần thức...
    color_primary: str = "#C040FF"
    color_secondary: str = "#FFFFFF"
    vfx_lock: str                      # mô tả VFX tiếng Anh, chèn NGUYÊN VĂN vào mọi shot của chiêu
    phases_hint: Optional[str] = None  # chiêu thường diễn ra thế nào
    sfx_charge: str = "charge"
    sfx_release: str = "energy_release"
    sfx_impact: str = "impact_heavy"


class Bible(BaseModel):
    style_lock: str = (
        "2D anime cel-shaded style matching the source manhua line art, "
        "consistent character design, cinematic lighting"
    )
    negative: str = "no text, no speech bubbles, no captions, no watermark, not 3D, not photorealistic"
    characters: list[Character] = []
    techniques: list[Technique] = []

    def character(self, cid: str) -> Optional[Character]:
        return next((c for c in self.characters if c.id == cid), None)

    def technique(self, tid: Optional[str]) -> Optional[Technique]:
        if not tid:
            return None
        return next((t for t in self.techniques if t.id == tid), None)


# ---------------------------------------------------------------------------
# Sequence & Shot: kế hoạch phim
# ---------------------------------------------------------------------------
class SequenceKind(str, Enum):
    dialogue = "dialogue"
    action = "action"
    technique = "technique"            # 1 chiêu thức có thể trải trên nhiều panel
    establishing = "establishing"
    transition = "transition"


class Phase(str, Enum):
    establish = "establish"
    dialogue = "dialogue"
    reaction = "reaction"
    anticipation = "anticipation"      # lấy đà
    charge = "charge"                  # tụ lực
    release = "release"                # xuất chiêu  <- title card mặc định ở đây
    travel = "travel"                  # chiêu bay tới
    impact = "impact"                  # va chạm   <- impact frame, shake, boom
    aftermath = "aftermath"            # khói bụi, hậu quả
    transition = "transition"


class Treatment(str, Enum):
    veo = "veo"                        # video AI từ keyframe (đắt, cho cao trào)
    motion_still = "motion_still"      # ảnh + zoom/pan + VFX bằng ffmpeg (rẻ)
    hold = "hold"                      # giữ khung (cho thoại ngắn)
    cut = "cut"                        # bỏ


class Camera(BaseModel):
    shot_size: str = "medium"          # extreme_close_up / close_up / medium / wide / extreme_wide
    movement: str = "static"           # push_in / pull_out / pan_left / pan_right / tilt_up / tilt_down / orbit / shake / static
    angle: str = "eye_level"           # low / high / dutch / overhead / eye_level


class KeyframeSpec(BaseModel):
    source_panels: list[str] = []
    prompt: str = ""
    character_refs: list[str] = []     # id nhân vật -> đính kèm ref_images
    file: Optional[str] = None         # điền tự động: keyframes/SH001_start.png


class FX(BaseModel):
    """Hiệu ứng hậu kỳ tất định (ffmpeg) - không phụ thuộc AI."""
    type: str                          # flash | impact_frame | shake | hitstop | speedlines | zoom_punch | chromatic | glow | vignette | silence_before
    at: float = 0.0                    # giây tính từ đầu shot
    dur: float = 0.3
    intensity: float = 1.0
    color: Optional[str] = None        # cho speedlines/flash; mặc định lấy màu chiêu
    on_key: bool = False               # True: `at` tính tương đối so với khoảnh khắc "đinh" (key moment)


class AudioCue(BaseModel):
    kind: str                          # line | sfx | music
    text: Optional[str] = None         # cho line
    text_kind: Optional[TextKind] = None
    speaker: Optional[str] = None
    name: Optional[str] = None         # tên sfx (thư mục trong assets/sfx) hoặc mood nhạc
    at: float = 0.0
    gain_db: float = 0.0
    file: Optional[str] = None         # điền tự động sau TTS
    on_key: bool = False


class TitleCue(BaseModel):
    """Title card tên chiêu thức."""
    text: str
    technique_id: Optional[str] = None
    at: float = 0.0
    dur: float = 1.8
    style: str = "technique"           # technique | sfx | system
    on_key: bool = False


class Shot(BaseModel):
    id: str                            # "SH001"
    sequence_id: str
    panels: list[str] = []
    phase: Phase = Phase.establish
    treatment: Treatment = Treatment.motion_still
    duration: float = 3.0
    speed: float = 1.0                 # <1 = slow-motion cho clip veo
    intensity: int = Field(2, ge=1, le=5)
    camera: Camera = Camera()
    action: str = ""
    emotion: str = ""
    keyframe_start: KeyframeSpec = KeyframeSpec()
    keyframe_end: Optional[KeyframeSpec] = None
    key_at: Optional[float] = None     # khoảnh khắc "đinh" dự kiến (giây); hiệu ứng on_key bám theo
    auto_key: bool = True              # với clip Veo: tự dò khoảnh khắc bùng sáng thật trong clip
    chain_from_prev: bool = False      # khung đầu = khung cuối clip trước (giữ liên tục chiêu thức)
    video_prompt: str = ""
    fx: list[FX] = []
    audio: list[AudioCue] = []
    titles: list[TitleCue] = []
    clip: Optional[str] = None         # điền tự động: clips/SH001.mp4
    status: str = "planned"

    @field_validator("duration")
    @classmethod
    def _dur(cls, v: float) -> float:
        return max(0.5, min(float(v), 12.0))


class Sequence(BaseModel):
    id: str                            # "SQ01"
    kind: SequenceKind
    panels: list[str]
    summary: str = ""
    technique_id: Optional[str] = None
    continuous: bool = False           # True = các shot là 1 cú máy liên tục (chain frame)
    music_mood: Optional[str] = None


class ShotList(BaseModel):
    chapter: str
    sequences: list[Sequence] = []
    shots: list[Shot] = []

    def sequence(self, sid: str) -> Optional[Sequence]:
        return next((s for s in self.sequences if s.id == sid), None)

    def total_duration(self) -> float:
        # duration = thời lượng TRÊN MÀN HÌNH; clip nguồn cần duration*speed giây
        return sum(s.duration for s in self.shots if s.treatment != Treatment.cut)
