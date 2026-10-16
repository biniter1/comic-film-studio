"""Luật tất định áp lên shot list sau khi LLM trả về.

LLM hay quên/không nhất quán, nên những thứ BẮT BUỘC đúng được code ép lại ở đây:
1. Khóa style + nhân vật + VFX chiêu thức chèn nguyên văn vào mọi prompt  -> chiêu thức nhất quán.
2. Chiêu trải nhiều panel: các shot veo liên tiếp nối bằng khung cuối      -> chuyển động liên tục.
3. Tên chiêu -> title card trên màn hình, thoại -> TTS + phụ đề            -> đúng loại chữ.
4. Không sót lời thoại nào; kéo dài shot đủ thời gian đọc.
5. Bộ VFX mặc định theo phase (impact/release/charge) nếu LLM bỏ trống     -> cảnh hành động có lực.
6. Ngân sách Veo: chỉ giữ veo cho shot intensity cao nhất.
"""
from __future__ import annotations

from typing import Optional

from .schemas import (AudioCue, Bible, FX, Phase, PanelReading, Sequence, SequenceKind, Shot, ShotList,
                      TextKind, TitleCue, Treatment)

READ_CPS = 14.0          # ký tự/giây đọc phụ đề tiếng Việt
LINE_GAP = 0.35

SPOKEN = {TextKind.dialogue, TextKind.narration, TextKind.inner_thought}

# Bộ VFX mặc định theo phase - "bù trí tưởng tượng" của người đọc truyện
DEFAULT_FX: dict[Phase, list[dict]] = {
    Phase.charge: [
        {"type": "vignette", "at": 0.0, "dur": 99, "intensity": 0.6},
        {"type": "glow", "at": 0.0, "dur": 99, "intensity": 0.35},
    ],
    Phase.release: [
        {"type": "zoom_punch", "at": -1, "dur": 0.25, "intensity": 0.08},
        {"type": "flash", "at": -1, "dur": 0.35, "intensity": 0.8},
        {"type": "chromatic", "at": -1, "dur": 0.4, "intensity": 1.0},
        {"type": "speedlines", "at": -1, "dur": 1.2, "intensity": 0.7},
    ],
    Phase.impact: [
        {"type": "silence_before", "at": -1, "dur": 0.35},
        {"type": "impact_frame", "at": -1, "dur": 0.125},
        {"type": "hitstop", "at": -1, "dur": 0.18},
        {"type": "flash", "at": -1, "dur": 0.3, "intensity": 1.0},
        {"type": "shake", "at": -1, "dur": 0.7, "intensity": 1.0},
        {"type": "chromatic", "at": -1, "dur": 0.3, "intensity": 1.5},
    ],
}
# (tên, thời điểm, mốc): mốc start = từ đầu shot, end = lùi từ cuối shot, key = quanh khoảnh khắc đinh
DEFAULT_SFX = {
    Phase.charge: [("charge", 0.0, "start"), ("riser", -2.0, "end")],
    Phase.release: [("energy_release", 0.0, "key"), ("whoosh", -0.1, "key")],
    Phase.impact: [("sub_drop", -0.05, "key"), ("impact_heavy", 0.0, "key"), ("rumble", 0.2, "key")],
    Phase.aftermath: [("wind", 0.0, "start")],
}


def _key_moment(shot: Shot) -> float:
    """Thời điểm 'đinh' trong shot (khi at=-1): ~55% thời lượng cho release/impact."""
    return round(shot.duration * (0.55 if shot.phase in (Phase.release, Phase.impact) else 0.3), 2)


def _lock_text(bible: Bible, shot: Shot, technique_id: Optional[str]) -> str:
    parts = [f"STYLE: {bible.style_lock}."]
    for cid in dict.fromkeys(shot.keyframe_start.character_refs):
        c = bible.character(cid)
        if c:
            parts.append(f"CHARACTER {c.name}: {c.look_lock}.")
    t = bible.technique(technique_id)
    if t:
        parts.append(f"SKILL '{t.name}' VFX (keep identical in every shot): {t.vfx_lock}. "
                     f"Energy colour {t.color_primary} with {t.color_secondary} highlights.")
    return " ".join(parts)


def enforce(sl: ShotList, bible: Bible, readings: dict[str, PanelReading], cfg: dict) -> list[str]:
    """Sửa shot list tại chỗ. Trả về danh sách ghi chú những gì đã sửa."""
    notes: list[str] = []
    gen = cfg["generation"]
    technique_mode = cfg["text"].get("technique_mode", "card")

    # --- 0. id + key moment ------------------------------------------------
    for i, s in enumerate(sl.shots, 1):
        s.id = f"SH{i:03d}"
        if s.key_at is None:
            s.key_at = _key_moment(s)
        # LLM dùng at=-1 nghĩa là "đúng lúc đinh"
        for item in [*s.fx, *s.audio, *s.titles]:
            if item.at == -1 and not item.on_key:
                item.at, item.on_key = 0.0, True
    seq_of = {s.id: sl.sequence(s.sequence_id) for s in sl.shots}

    # --- 1. khóa prompt -----------------------------------------------------
    for s in sl.shots:
        seq = seq_of[s.id]
        tid = seq.technique_id if seq else None
        lock = _lock_text(bible, s, tid)
        for kf in (s.keyframe_start, s.keyframe_end):
            if kf and kf.prompt and "STYLE:" not in kf.prompt:
                kf.prompt = f"{kf.prompt.strip()} {lock} AVOID: {bible.negative}."
        if s.treatment == Treatment.veo and s.video_prompt and "STYLE:" not in s.video_prompt:
            s.video_prompt = f"{s.video_prompt.strip()} {lock} Keep line art and faces consistent with the input frames."

    # --- 2. chuỗi liên tục cho chiêu thức nhiều panel -------------------------
    for seq in sl.sequences:
        shots = [s for s in sl.shots if s.sequence_id == seq.id and s.treatment != Treatment.cut]
        if seq.kind in (SequenceKind.technique, SequenceKind.action) and seq.continuous:
            for prev, cur in zip(shots, shots[1:]):
                if prev.treatment == Treatment.veo and cur.treatment == Treatment.veo and not cur.chain_from_prev:
                    cur.chain_from_prev = True
                    notes.append(f"{cur.id}: nối khung cuối {prev.id} (chiêu liên tục)")

    # --- 2b. match cut: ảnh tĩnh ngay trước clip Veo cùng khung đầu -> kết thúc đúng khung đó
    for prev, cur in zip(sl.shots, sl.shots[1:]):
        if (prev.treatment == Treatment.motion_still and cur.treatment == Treatment.veo and not cur.chain_from_prev
                and prev.keyframe_start.source_panels == cur.keyframe_start.source_panels
                and prev.camera.movement in ("push_in", "static")):
            prev.camera.movement = "pull_out"
            cur.keyframe_start.prompt = prev.keyframe_start.prompt   # dùng chung 1 keyframe
            notes.append(f"{prev.id}: đổi push_in -> pull_out để khớp khung đầu {cur.id} (match cut)")

    # --- 3. chữ: tên chiêu -> title card, thoại -> line -----------------------
    for seq in sl.sequences:
        shots = [s for s in sl.shots if s.sequence_id == seq.id and s.treatment != Treatment.cut]
        if not shots:
            continue
        texts = [(pid, t) for pid in seq.panels for t in (readings.get(pid).texts if readings.get(pid) else [])]
        existing_titles = {tc.text.strip().lower() for s in shots for tc in s.titles}
        existing_lines = {a.text.strip().lower() for s in shots for a in s.audio if a.kind == "line" and a.text}

        for pid, t in texts:
            key = t.text.strip().lower()
            if t.kind == TextKind.technique_name:
                # chiêu không bao giờ là phụ đề thường
                for s in shots:
                    before = len(s.audio)
                    s.audio = [a for a in s.audio if not (a.kind == "line" and a.text and a.text.strip().lower() == key
                                                          and technique_mode == "card")]
                    if len(s.audio) != before:
                        notes.append(f"{s.id}: '{t.text}' chuyển từ phụ đề sang title card")
                if key not in existing_titles:
                    # ưu tiên: xuất chiêu > trúng đòn > shot chứa panel có chữ > tụ lực > shot đầu
                    target = next((s for s in shots if s.phase == Phase.release), None) \
                        or next((s for s in shots if s.phase == Phase.impact), None) \
                        or next((s for s in shots if pid in s.panels), None) \
                        or next((s for s in shots if s.phase == Phase.charge), shots[0])
                    target.titles.append(TitleCue(text=t.text, technique_id=seq.technique_id,
                                                  at=-0.15, on_key=True))
                    existing_titles.add(key)
                    notes.append(f"{target.id}: thêm title card '{t.text}'")
                if technique_mode == "card+voice" and key not in existing_lines:
                    target = next(s for s in shots if any(tc.text.strip().lower() == key for tc in s.titles))
                    target.audio.append(AudioCue(kind="line", text=t.text, text_kind=TextKind.technique_name,
                                                 speaker=t.speaker, at=-0.4, on_key=True))
            elif t.kind in SPOKEN and key not in existing_lines:
                target = next((s for s in shots if pid in s.panels), shots[0])
                target.audio.append(AudioCue(kind="line", text=t.text, text_kind=t.kind, speaker=t.speaker, at=-1))
                existing_lines.add(key)
                notes.append(f"{target.id}: bổ sung thoại bị sót '{t.text[:30]}'")
            elif t.kind == TextKind.sfx and cfg["text"].get("sfx_text", True) and key not in existing_titles:
                target = next((s for s in shots if pid in s.panels), shots[0])
                target.titles.append(TitleCue(text=t.text, at=0.05, dur=0.9, style="sfx", on_key=True))
                existing_titles.add(key)
            elif t.kind == TextKind.system and key not in existing_titles:
                target = next((s for s in shots if pid in s.panels), shots[0])
                target.titles.append(TitleCue(text=t.text, at=0.3, dur=max(2.0, len(t.text) / READ_CPS + 1), style="system"))
                existing_titles.add(key)

    # --- 4. xếp lịch thoại + kéo dài shot đủ đọc ------------------------------
    for s in sl.shots:
        lines = [a for a in s.audio if a.kind == "line" and not a.on_key]
        t = 0.3
        for a in sorted(lines, key=lambda a: (a.at < 0, a.at)):
            if a.at < 0 or a.at < t:
                a.at = round(t, 2)
            t = a.at + len(a.text or "") / READ_CPS + LINE_GAP
        need = t + 0.2 if lines else 0
        if need > s.duration:
            if s.treatment == Treatment.veo:
                notes.append(f"{s.id}: thoại dài {need:.1f}s > clip, sẽ giữ khung cuối để đủ đọc")
            s.duration = round(need, 2)

    # --- 5. VFX/SFX mặc định theo phase ---------------------------------------
    if cfg.get("auto_fx", True):
        for s in sl.shots:
            seq = seq_of[s.id]
            if not seq or seq.kind not in (SequenceKind.technique, SequenceKind.action):
                continue
            tcolor = (bible.technique(seq.technique_id).color_primary if bible.technique(seq.technique_id) else None)
            have = {f.type for f in s.fx}
            for spec in DEFAULT_FX.get(s.phase, []):
                if spec["type"] in have:
                    continue
                if spec["at"] == -1:          # bám khoảnh khắc đinh
                    at = -spec["dur"] if spec["type"] == "silence_before" else 0.0
                    s.fx.append(FX(type=spec["type"], at=at, dur=spec["dur"], intensity=spec.get("intensity", 1.0),
                                   color=tcolor if spec["type"] in ("speedlines", "glow") else None, on_key=True))
                else:
                    s.fx.append(FX(type=spec["type"], at=spec["at"], dur=min(spec["dur"], s.duration),
                                   intensity=spec.get("intensity", 1.0),
                                   color=tcolor if spec["type"] in ("speedlines", "glow") else None))
            have_sfx = {a.name for a in s.audio if a.kind == "sfx"}
            for name, at, anchor in DEFAULT_SFX.get(s.phase, []):
                if name in have_sfx:
                    continue
                if anchor == "key":
                    s.audio.append(AudioCue(kind="sfx", name=name, at=at, on_key=True))
                else:
                    s.audio.append(AudioCue(kind="sfx", name=name, at=max(0.0, s.duration + at if anchor == "end" else at)))

    # --- 6. ngân sách Veo -----------------------------------------------------
    budget = int(gen.get("veo_budget_per_chapter", 12))
    veo = [s for s in sl.shots if s.treatment == Treatment.veo]
    if len(veo) > budget:
        keep = {s.id for s in sorted(veo, key=lambda s: (-s.intensity, s.id))[:budget]}
        for i, s in enumerate(sl.shots):
            if s.treatment == Treatment.veo and s.id not in keep:
                s.treatment = Treatment.motion_still
                s.keyframe_end = None
                notes.append(f"{s.id}: hạ veo -> motion_still (vượt ngân sách {budget})")
                if i + 1 < len(sl.shots):
                    sl.shots[i + 1].chain_from_prev = False
    for i, s in enumerate(sl.shots):
        if s.chain_from_prev and (i == 0 or sl.shots[i - 1].treatment != Treatment.veo):
            s.chain_from_prev = False

    # --- 7. đường dẫn file chuẩn ---------------------------------------------
    for s in sl.shots:
        s.keyframe_start.file = f"keyframes/{s.id}_start.png"
        if s.keyframe_end:
            s.keyframe_end.file = f"keyframes/{s.id}_end.png"
        if s.treatment == Treatment.veo:
            s.clip = f"clips/{s.id}.mp4"
    return notes


def veo_gen_seconds(duration: float, speed: float, allowed: list[int]) -> int:
    """Độ dài clip cần tạo trên Veo (đã tính slow-mo)."""
    need = duration * speed
    return next((d for d in sorted(allowed) if d >= need - 0.05), max(allowed))
