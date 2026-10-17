"""Phase 2c — deterministic rules applied after the AI returns shots (SPEC §4.3) and the prompt
composer (SPEC §4.6). Pure functions over plain dicts so they are easy to test; the DB layer lives
in app/analysis/shots.py."""

from dataclasses import dataclass, field
from typing import Any

READ_CPS = 14.0  # characters per second when reading subtitles
LINE_GAP_S = 0.3
SPOKEN = ("dialogue", "inner_thought", "narration")
DEFAULT_STYLE = (
    "2D anime cel-shaded film still, clean line art matching the source manhua, "
    "cinematic lighting, detailed background"
)
DEFAULT_NEGATIVE = "No text, no speech bubbles, no captions, no watermark."
MAX_VIDEO_WORDS = 90


@dataclass
class CharInfo:
    key: str
    name: str
    role: str = "supporting"  # main | supporting | extra
    is_group: bool = False
    look_lock: str = ""
    outfits: dict[str, dict[str, Any]] = field(default_factory=dict)  # key → outfit dict
    default_outfit: str | None = None


@dataclass
class LocInfo:
    key: str
    name: str
    location_lock: str = ""
    sheet_asset_id: str | None = None  # only when approved


@dataclass
class Ctx:
    """Everything the rules need about one chapter."""

    frame_scene: dict[str, str]  # frame_id → scene_id
    frame_asset: dict[str, str]  # frame_id → asset_id
    frame_chars: dict[str, list[str]]  # frame_id → character keys seen by `read`
    lines: dict[str, dict[str, Any]]  # line_id → line dict (kind, text, anchor_frame_id, order)
    chars: dict[str, CharInfo]
    locs: dict[str, LocInfo]
    style_lock: str = DEFAULT_STYLE
    negative: str = DEFAULT_NEGATIVE
    clip_seconds: float = 4.0
    max_ref_images: int = 4


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------
def reading_time(texts: list[str]) -> float:
    if not texts:
        return 0.0
    return sum(max(1.2, len(t) / READ_CPS) for t in texts) + LINE_GAP_S * (len(texts) - 1)


def assign_lines(shots: list[dict], scene_frames: list[str], ctx: Ctx) -> None:
    """Rule 1 + 2: titles for technique/system/sfx; every spoken line of the scene ends up in
    exactly one shot (AI choice first, else the shot showing its anchor frame)."""
    scene_set = set(scene_frames)
    scene_lines = [lid for lid, ln in ctx.lines.items() if ln.get("anchor_frame_id") in scene_set]
    taken: set[str] = set()
    for sh in shots:
        keep = []
        for lid in sh.get("line_ids", []):
            if lid in ctx.lines and lid not in taken and lid in scene_lines:
                keep.append(lid)
                taken.add(lid)
        sh["line_ids"] = keep
    for lid in sorted(scene_lines, key=lambda x: ctx.lines[x].get("order", 0)):
        if lid in taken:
            continue
        anchor = ctx.lines[lid].get("anchor_frame_id")
        target = next((s for s in shots if anchor in s.get("frame_ids", [])), None)
        if target is None:
            target = shots[0]
        target.setdefault("line_ids", []).append(lid)
        target.setdefault("rule_notes", []).append(
            f"Bổ sung câu bị sót: “{ctx.lines[lid]['text'][:40]}”"
        )
        taken.add(lid)
    for sh in shots:
        sh["line_ids"].sort(key=lambda x: ctx.lines[x].get("order", 0))
        titles = []
        for lid in sh["line_ids"]:
            ln = ctx.lines[lid]
            kind = ln.get("kind")
            if kind == "technique_name":
                titles.append({"text": ln["text"], "style": "technique", "line_id": lid})
            elif kind == "system":
                titles.append({"text": ln["text"], "style": "system", "line_id": lid})
            elif kind == "sfx":
                titles.append({"text": ln["text"], "style": "sfx", "line_id": lid})
        sh["titles"] = titles


def fix_duration(sh: dict, ctx: Ctx) -> None:
    """Rule 5: long enough to read the subtitles."""
    texts = [ctx.lines[lid]["text"] for lid in sh["line_ids"] if ctx.lines[lid]["kind"] in SPOKEN]
    need = round(reading_time(texts) + 0.5, 1) if texts else 0.0
    if need > sh["duration_s"]:
        sh.setdefault("rule_notes", []).append(
            f"Kéo dài {sh['duration_s']:.1f}s → {need:.1f}s cho đủ thời gian đọc thoại"
        )
        sh["duration_s"] = need
    if sh["duration_s"] > ctx.clip_seconds * 1.5:
        sh.setdefault("rule_notes", []).append(
            f"Shot dài {sh['duration_s']:.1f}s (> {ctx.clip_seconds * 1.5:.0f}s): "
            "nên tách shot hoặc thêm shot phản ứng"
        )


def fix_beats(sh: dict) -> None:
    """Rule 8: beats cover [0, duration] contiguously; ≤ 3 beats for clips ≤ 5s."""
    dur = float(sh["duration_s"])
    beats = sorted(
        [b for b in sh.get("beats", []) if str(b.get("action", "")).strip()],
        key=lambda b: float(b.get("t0", 0)),
    )
    if not beats:
        beats = [{"t0": 0.0, "t1": dur, "action": sh.get("action") or "subtle idle motion"}]
        sh.setdefault("rule_notes", []).append("Không có nhịp — tạo 1 nhịp từ hành động")
    limit = 3 if dur <= 5 else 5
    if len(beats) > limit:
        extra = beats[limit - 1 :]
        beats = beats[: limit - 1] + [
            {"t0": extra[0]["t0"], "t1": dur, "action": "; ".join(b["action"] for b in extra)}
        ]
        sh.setdefault("rule_notes", []).append(f"Gộp nhịp thừa (tối đa {limit})")
    fixed = []
    t = 0.0
    for i, b in enumerate(beats):
        t1 = dur if i == len(beats) - 1 else min(max(float(b.get("t1", 0)), t + 0.3), dur)
        fixed.append({"t0": round(t, 2), "t1": round(t1, 2), "action": str(b["action"]).strip()})
        t = t1
    sh["beats"] = fixed


def fix_blocking(sh: dict, ctx: Ctx) -> None:
    """Rule 9: known characters, valid outfit, flag invented characters / missing looks."""
    seen_in_frames = {k for f in sh.get("frame_ids", []) for k in ctx.frame_chars.get(f, [])}
    out = []
    for b in sh.get("blocking", []):
        key = b.get("character_key")
        ch = ctx.chars.get(key or "")
        notes = sh.setdefault("rule_notes", [])
        if ch is None:
            notes.append(f"Nhân vật “{key}” chưa có trong thư viện nhân vật")
            out.append(b)
            continue
        if not b.get("outfit_key") or b["outfit_key"] not in ch.outfits:
            b["outfit_key"] = ch.default_outfit
        if not ch.is_group and not ch.look_lock:
            notes.append(f"{ch.name}: chưa có mô tả ngoại hình (look_lock)")
        if seen_in_frames and key not in seen_in_frames and not sh.get("inserted"):
            notes.append(f"AI tự thêm nhân vật {ch.name} (không thấy trong khung gốc)")
        out.append(b)
    sh["blocking"] = out


def fix_transitions_and_chains(shots: list[dict], scene_of: dict[int, str]) -> None:
    """Rule 4 + chain building: continuous only right after a shot of the same scene."""
    chain = 0
    pos = 0
    for i, sh in enumerate(shots):
        if sh["transition_in"] == "continuous" and (i == 0 or scene_of[i] != scene_of[i - 1]):
            sh["transition_in"] = "cut"
            sh.setdefault("rule_notes", []).append(
                "“continuous” không hợp lệ ở đầu scene → đổi thành cut"
            )
        if sh["transition_in"] == "continuous":
            pos += 1
        else:
            chain += 1
            pos = 1
        sh["chain_code"] = f"C{chain:02d}"
        sh["chain_pos"] = pos


def check_axis(shots: list[dict], scene_of: dict[int, str]) -> None:
    """Rule 10: same two characters swap left/right between consecutive shots of a scene."""

    def sides(sh: dict) -> dict[str, str]:
        return {
            b["character_key"]: b["screen_pos"]
            for b in sh.get("blocking", [])
            if b.get("screen_pos") in ("left", "right")
        }

    for i in range(1, len(shots)):
        if scene_of[i] != scene_of[i - 1]:
            continue
        a, b = sides(shots[i - 1]), sides(shots[i])
        common = [k for k in a if k in b]
        for x in range(len(common)):
            for y in range(x + 1, len(common)):
                p, q = common[x], common[y]
                if a[p] != a[q] and b[p] != b[q] and a[p] == b[q]:
                    shots[i].setdefault("rule_notes", []).append(
                        f"Có thể lật trục 180°: {p} và {q} đổi trái/phải so với shot trước"
                    )


def apply_rules(scenes: list[dict], shots_by_scene: dict[str, list[dict]], ctx: Ctx) -> list[dict]:
    """Run every rule over the whole chapter; returns the flat ordered shot list."""
    flat: list[dict] = []
    scene_of: dict[int, str] = {}
    for sc in scenes:
        shots = shots_by_scene.get(sc["id"], [])
        if not shots:
            continue
        for sh in shots:
            sh.setdefault("rule_notes", [])
            sh.setdefault("line_ids", [])
            sh["frame_ids"] = [f for f in sh.get("frame_ids", []) if f in ctx.frame_asset]
            if not sh.get("location_key"):
                sh["location_key"] = sc.get("location_key")
        assign_lines(shots, sc["frame_ids"], ctx)
        for sh in shots:
            fix_duration(sh, ctx)
            fix_beats(sh)
            fix_blocking(sh, ctx)
            scene_of[len(flat)] = sc["id"]
            flat.append(sh)
    fix_transitions_and_chains(flat, scene_of)
    check_axis(flat, scene_of)
    for i, sh in enumerate(flat, 1):
        sh["order"] = i
        sh["code"] = f"SH{i:03d}"
    return flat


# ---------------------------------------------------------------------------
# prompt composer (SPEC §4.6) — code builds prompts, never the model
# ---------------------------------------------------------------------------
_ROLE_RANK = {"main": 0, "supporting": 1, "extra": 2}
_SIZE_TXT = {
    "extreme_wide": "extreme wide shot",
    "wide": "wide shot",
    "full": "full shot",
    "medium": "medium shot",
    "medium_close_up": "medium close-up",
    "close_up": "close-up",
    "extreme_close_up": "extreme close-up",
    "insert": "insert detail shot",
}
_ANGLE_TXT = {
    "eye": "eye-level",
    "low": "low-angle",
    "high": "high-angle",
    "overhead": "overhead",
    "dutch": "dutch-angle",
}
_MOVE_TXT = {
    "static": "Static camera",
    "push_in": "Push in",
    "pull_out": "Pull out",
    "pan_left": "Pan left",
    "pan_right": "Pan right",
    "tilt_up": "Tilt up",
    "tilt_down": "Tilt down",
    "truck_left": "Truck left",
    "truck_right": "Truck right",
    "orbit_left": "Orbit left",
    "orbit_right": "Orbit right",
    "follow": "Tracking follow",
    "crane_up": "Crane up",
    "crane_down": "Crane down",
    "handheld_shake": "Handheld shake",
    "crash_zoom": "Crash zoom",
}
_POS_TXT = {"left": "on the left", "center": "in the center", "right": "on the right"}
_DEPTH_TXT = {"fg": "foreground", "mg": "midground", "bg": "background"}
_FACING_TXT = {
    "left": "facing left",
    "right": "facing right",
    "camera": "facing the camera",
    "away": "facing away",
}


def _outfit(ctx: Ctx, b: dict) -> dict[str, Any]:
    ch = ctx.chars.get(b.get("character_key", ""))
    if not ch:
        return {}
    return ch.outfits.get(b.get("outfit_key") or "", {}) or ch.outfits.get(
        ch.default_outfit or "", {}
    )


def compose(sh: dict, ctx: Ctx) -> None:
    cam = sh.get("camera", {})
    # --- attachments: panel → sheets (main, then supporting) → location sheet -----------
    att: list[dict[str, Any]] = []
    panel = next((f for f in sh.get("frame_ids", []) if f in ctx.frame_asset), None)
    if panel:
        att.append({"kind": "frame", "asset_id": ctx.frame_asset[panel], "label": "comic panel"})
    ordered = sorted(
        sh.get("blocking", []),
        key=lambda b: _ROLE_RANK.get(
            getattr(ctx.chars.get(b.get("character_key", "")), "role", "extra"), 3
        ),
    )
    sheet_of: dict[str, int] = {}
    for b in ordered:
        ch = ctx.chars.get(b.get("character_key", ""))
        if not ch or ch.is_group or ch.role == "extra" or len(att) >= ctx.max_ref_images:
            continue
        sheet = _outfit(ctx, b).get("sheet_asset_id")
        if sheet:
            att.append(
                {"kind": "char_sheet", "asset_id": sheet, "label": f"character sheet of {ch.name}"}
            )
            sheet_of[ch.key] = len(att)
    loc = ctx.locs.get(sh.get("location_key") or "")
    loc_img = None
    if loc and loc.sheet_asset_id and len(att) < ctx.max_ref_images:
        att.append(
            {
                "kind": "location_sheet",
                "asset_id": loc.sheet_asset_id,
                "label": f"location sheet of {loc.name}",
            }
        )
        loc_img = len(att)
    sh["attachments"] = att

    # --- keyframe prompt (Nano Banana) ---------------------------------------------------
    lines: list[str] = []
    if panel:
        lines.append("Image 1 is the comic panel: copy its composition, poses and camera angle.")
    else:
        lines.append("This is a NEW shot that is not drawn in the comic.")
    for key, idx in sheet_of.items():
        lines.append(f"Image {idx} is the character sheet of {ctx.chars[key].name}.")
    if loc_img:
        lines.append(f"Image {loc_img} is the location sheet of {loc.name}.")  # type: ignore[union-attr]
    lines.append(
        f"{ctx.style_lock}. {_SIZE_TXT.get(cam.get('shot_size', 'medium'), 'medium shot')}, "
        f"{_ANGLE_TXT.get(cam.get('angle', 'eye'), 'eye-level')} angle. 16:9 frame."
    )
    if loc and loc.location_lock:
        lines.append(f"Location: {loc.location_lock}.")
    for b in sh.get("blocking", []):
        ch = ctx.chars.get(b.get("character_key", ""))
        name = ch.name if ch else b.get("character_key", "someone")
        look = ch.look_lock if ch and ch.look_lock else ""
        outfit = _outfit(ctx, b).get("outfit_lock") or ""
        parts = [p for p in (look, f"wearing {outfit}" if outfit else "") if p]
        where = (
            f"{_POS_TXT.get(b.get('screen_pos', 'center'))} "
            f"{_DEPTH_TXT.get(b.get('depth', 'mg'))}, {_FACING_TXT.get(b.get('facing', 'camera'))}"
        )
        pose = f", {b['pose']}" if b.get("pose") else ""
        desc = f" ({'; '.join(parts)})" if parts else ""
        if ch and (ch.is_group or ch.role == "extra"):
            lines.append(f"In the background: {name}{desc}, {where}{pose}.")
        else:
            lines.append(f"{name}{desc}: {where}{pose}.")
    if sh.get("start_state"):
        lines.append(f"Moment: {sh['start_state']}.")
    if sheet_of:
        lines.append("Keep faces, hairstyles and outfits exactly as in the character sheets.")
    lines.append(ctx.negative)
    sh["keyframe_prompt"] = "\n".join(lines)

    # --- video prompt (Muse: start image only) ------------------------------------------
    move = _MOVE_TXT.get(cam.get("movement", "static"), "Static camera")
    speed = cam.get("speed", "slow")
    head = f"{move}, {speed}, {_SIZE_TXT.get(cam.get('shot_size', 'medium'), 'medium shot')}."
    beats = sh.get("beats", [])
    words = ["First", "Then", "Finally"] if len(beats) >= 3 else ["First", "Finally"]
    beat_txt = []
    for i, bt in enumerate(beats):
        lead = "Then" if 0 < i < len(beats) - 1 else words[0] if i == 0 else "Finally"
        if len(beats) == 1:
            lead = ""
        beat_txt.append(f"{lead + ', ' if lead else ''}{bt['action'].rstrip('.')}.")
    ids = []
    for b in sh.get("blocking", []):
        o = _outfit(ctx, b)
        ch = ctx.chars.get(b.get("character_key", ""))
        if ch and not ch.is_group and ch.role != "extra":
            ids.append(o.get("short_id") or ch.name)
    tail = (
        f"{', '.join(ids)} keep{'s' if len(ids) == 1 else ''} the same face and outfit throughout. "
        if ids
        else ""
    )
    end = f"Ends on: {sh['end_state'].rstrip('.')}. " if sh.get("end_state") else ""
    video = f"{head} {' '.join(beat_txt)} {end}{tail}No new characters, no text, no cuts."
    video = " ".join(video.split())
    if len(video.split()) > MAX_VIDEO_WORDS and tail:
        video = " ".join(
            f"{head} {' '.join(beat_txt)} {end}No new characters, no text, no cuts.".split()
        )
        sh.setdefault("rule_notes", []).append("Prompt video dài — đã bỏ câu nhận diện nhân vật")
    if len(video.split()) > MAX_VIDEO_WORDS:
        sh.setdefault("rule_notes", []).append(
            f"Prompt video {len(video.split())} từ (> {MAX_VIDEO_WORDS}) — "
            "Muse có thể bỏ qua phần cuối"
        )
    sh["video_prompt"] = video
