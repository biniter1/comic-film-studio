"""Phase 2a analysis stages: `read` (frame types + raw dialogue + speakers) and `dialogue` (polish).

Both stages are split into UNITS (a batch of frames / a chunk of lines). A unit can be produced
by the API provider (job) or pasted by the user (manual mode) — both go through the same
`apply_*_unit` + finalize code, so results are identical (SPEC §4.2).
"""

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app import db
from app.analysis.engine import load_prompt, parse_and_validate
from app.analysis.glossary import (
    apply_glossary,
    approved_terms,
    merge_address_candidates,
    merge_glossary_candidates,
)
from app.analysis.schemas import DialogueOut, ReadBatchOut
from app.config import settings
from app.errors import AppError
from app.frames.images import _jpeg_bytes
from app.jobs.event_bus import event_bus
from app.models.analysis import AddressRule, AnalysisRun, Character, CharacterOutfit, DialogueLine
from app.models.project import Asset, Chapter, Frame
from app.providers.base import ImagePart, ProviderRequest
from app.storage import asset_abs_path, chapter_dir

PROMPT_VERSION = "v2"
READ_BATCH = 6
DIALOGUE_CHUNK = 150
DIALOGUE_CONTEXT = 10
LENGTH_TOLERANCE = 0.4
LOW_CONFIDENCE = 0.7
POLISHABLE_KINDS = ("dialogue", "inner_thought", "narration", "technique_name", "system")
ANALYZABLE_STATUSES = ("frames_approved", "analyzing", "dialogue_draft", "dialogue_approved")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session() -> Session:
    return Session(db.engine)


def work_dir(ch: Chapter) -> Path:
    d = chapter_dir(ch.project_id, ch.id) / "analysis"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _chapter(s: Session, cid: str) -> Chapter:
    ch = s.get(Chapter, cid)
    if not ch:
        raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
    return ch


def _frames(s: Session, cid: str) -> list[Frame]:
    return list(s.exec(select(Frame).where(Frame.chapter_id == cid).order_by(Frame.idx)))


def _emit(ch: Chapter) -> None:
    event_bus.publish_threadsafe(
        "chapter.updated", {"id": ch.id, "project_id": ch.project_id, "status": ch.status}
    )


def _characters(s: Session, pid: str) -> list[Character]:
    return list(s.exec(select(Character).where(Character.project_id == pid)))


def assert_analyzable(cid: str) -> Chapter:
    with _session() as s:
        ch = _chapter(s, cid)
        if ch.status not in ANALYZABLE_STATUSES:
            raise AppError(
                "FRAMES_NOT_APPROVED",
                "Hãy duyệt khung (màn Khung → Duyệt khung) trước khi phân tích",
                status_code=409,
            )
        return ch


def _set_status(cid: str, status: str) -> None:
    with _session() as s:
        ch = _chapter(s, cid)
        ch.status = status
        ch.updated_at = _now()
        s.add(ch)
        s.commit()
        s.refresh(ch)
        _emit(ch)


# ===========================================================================
# READ
# ===========================================================================
def read_units(cid: str) -> list[list[str]]:
    with _session() as s:
        ids = [f.id for f in _frames(s, cid)]
    return [ids[i : i + READ_BATCH] for i in range(0, len(ids), READ_BATCH)]


def reset_dialogue(cid: str) -> int:
    """Start a fresh read: back up existing lines, then delete them and old runs."""
    with _session() as s:
        ch = _chapter(s, cid)
        lines = list(s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)))
        if lines:
            hist = work_dir(ch) / "history"
            hist.mkdir(exist_ok=True)
            (hist / f"dialogue_{_now().strftime('%Y%m%d-%H%M%S')}.json").write_text(
                json.dumps(
                    [d.model_dump(mode="json") for d in lines], ensure_ascii=False, indent=1
                ),
                encoding="utf-8",
            )
        for d in lines:
            s.delete(d)
        for r in s.exec(select(AnalysisRun).where(AnalysisRun.chapter_id == cid)):
            s.delete(r)
        ch.status = "analyzing"
        s.add(ch)
        s.commit()
        return len(lines)


def build_read_request(cid: str, unit_index: int) -> tuple[ProviderRequest, list[str]]:
    with _session() as s:
        ch = _chapter(s, cid)
        frames = _frames(s, cid)
        ids = [f.id for f in frames]
        targets = read_units(cid)[unit_index]
        first, last = ids.index(targets[0]), ids.index(targets[-1])
        ctx_prev = frames[first - 1] if first > 0 else None
        ctx_next = frames[last + 1] if last + 1 < len(frames) else None
        by_id = {f.id: f for f in frames}

        def img(f: Frame, role: str) -> ImagePart:
            a = s.get(Asset, f.asset_id)
            assert a
            return ImagePart(f"FRAME {f.id} ({role})", asset_abs_path(ch.project_id, a.path))

        images = []
        if ctx_prev:
            images.append(img(ctx_prev, "CONTEXT — previous frame, do not return"))
        images += [img(by_id[i], "TARGET") for i in targets]
        if ctx_next:
            images.append(img(ctx_next, "CONTEXT — next frame, do not return"))

        prev_run = s.exec(
            select(AnalysisRun).where(
                AnalysisRun.chapter_id == cid,
                AnalysisRun.stage == "read",
                AnalysisRun.unit_index == unit_index - 1,
            )
        ).first()
        summary = (prev_run.payload or {}).get("summary", "") if prev_run else ""
        chars = [
            {"key": c.key, "name": c.name, "aliases": c.aliases, "gender": c.gender}
            for c in _characters(s, ch.project_id)
            if c.status != "rejected"
        ]
        terms = [{"term": t.term, "kind": t.kind} for t in approved_terms(s, ch.project_id)]
    user = json.dumps(
        {
            "TARGET_FRAMES": targets,
            "CONTEXT_FRAMES": [f.id for f in (ctx_prev, ctx_next) if f],
            "KNOWN_CHARACTERS": chars,
            "GLOSSARY": terms,
            "RUNNING_SUMMARY": summary or "Start of chapter.",
        },
        ensure_ascii=False,
        indent=1,
    )
    req = ProviderRequest(
        stage="read",
        model=settings.analysis_model_vision,
        system=load_prompt("read", PROMPT_VERSION),
        user_text=user,
        images=images,
    )
    return req, targets


def read_validator(targets: list[str]):
    def check(out: ReadBatchOut) -> None:
        got = [f.frame_id for f in out.frames]
        if got != targets:
            raise ValueError(f"'frames' must contain exactly {targets} in this order, got {got}")

    return check


def apply_read_unit(
    cid: str, unit_index: int, out: ReadBatchOut, *, mode: str, attempts: int, ih: str | None
) -> None:
    with _session() as s:
        ch = _chapter(s, cid)
        frames = {f.id: f for f in _frames(s, cid)}
        targets = [fr.frame_id for fr in out.frames]
        for d in s.exec(select(DialogueLine).where(DialogueLine.source_frame_id.in_(targets))):
            s.delete(d)
        for fr in out.frames:
            f = frames[fr.frame_id]
            f.reading = fr.model_dump(mode="json", exclude={"texts"})
            if f.frame_type_source != "user":
                f.frame_type = fr.frame_type
                f.frame_type_source = "ai"
            s.add(f)
            if f.frame_type == "credit":
                continue  # translator banners / ads: no dialogue
            for t in fr.texts:
                s.add(
                    DialogueLine(
                        chapter_id=cid,
                        order=0,
                        source_frame_id=f.id,
                        line_no=t.line_no,
                        kind=t.kind,
                        speaker_key=t.speaker_key,
                        speaker_label=t.speaker_label,
                        speaker_gender=t.speaker_gender,
                        speaker_age=t.speaker_age,
                        speaker_confidence=t.speaker_confidence,
                        belongs_to=t.belongs_to,
                        text_raw=t.text,
                        text=t.text,
                        needs_review=t.kind in ("dialogue", "inner_thought")
                        and t.speaker_confidence < LOW_CONFIDENCE,
                    )
                )
        known = {c.key for c in _characters(s, ch.project_id)}
        for nc in out.new_characters:
            if nc.key in known:
                continue
            char = Character(
                project_id=ch.project_id,
                key=nc.key,
                name=nc.name,
                aliases=nc.aliases,
                gender=nc.gender,
                age_group=nc.age_group,
                voice_style=nc.voice_style,
            )
            s.add(char)
            s.flush()
            s.add(
                CharacterOutfit(
                    character_id=char.id,
                    key="default",
                    name_vi="Mặc định",
                    outfit_lock="",
                    short_id="",
                    is_default=True,
                    sheet_status="missing",
                )
            )
            known.add(nc.key)
        _upsert_run(
            s,
            cid,
            "read",
            unit_index,
            mode=mode,
            status="succeeded",
            attempts=attempts,
            ih=ih,
            payload={"targets": targets, "summary": out.running_summary},
        )
        s.commit()


def _upsert_run(s: Session, cid: str, stage: str, unit_index: int, **kw: Any) -> AnalysisRun:
    run = s.exec(
        select(AnalysisRun).where(
            AnalysisRun.chapter_id == cid,
            AnalysisRun.stage == stage,
            AnalysisRun.unit_index == unit_index,
        )
    ).first() or AnalysisRun(chapter_id=cid, stage=stage, unit_index=unit_index)
    run.mode = kw.get("mode", run.mode)
    run.status = kw.get("status", run.status)
    run.attempts = kw.get("attempts", run.attempts)
    run.input_hash = kw.get("ih", run.input_hash)
    run.error = kw.get("error")
    run.provider = kw.get("provider", run.provider)
    run.model = kw.get("model", run.model)
    run.prompt_version = PROMPT_VERSION
    if "payload" in kw:
        run.payload = {**(run.payload or {}), **kw["payload"]}
    if run.status in ("succeeded", "failed"):
        run.finished_at = _now()
    s.add(run)
    return run


def compute_anchor(frames: list[Frame], i: int, direction: str) -> str | None:
    """Scene frame a line from frames[i] is shown with (SPEC §4.5)."""
    if frames[i].frame_type in (None, "scene"):
        return frames[i].id
    before = [f for f in reversed(frames[:i]) if f.frame_type == "scene"]
    after = [f for f in frames[i + 1 :] if f.frame_type == "scene"]
    order = (after, before) if direction == "next" else (before, after)
    for side in order:
        if side:
            return side[0].id
    return None


def finalize_read(cid: str) -> None:
    """Global reading order, anchors, speaker sanity. Safe to call repeatedly."""
    with _session() as s:
        ch = _chapter(s, cid)
        recompute_anchors(s, cid)
        keys = {c.key for c in _characters(s, ch.project_id)}
        for d in s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)):
            if d.speaker_key and d.speaker_key not in keys:
                d.speaker_label = d.speaker_label or d.speaker_key
                d.speaker_key = None
                s.add(d)
        ch.status = "dialogue_draft"
        ch.updated_at = _now()
        s.add(ch)
        s.commit()
        s.refresh(ch)
        _emit(ch)


def recompute_anchors(s: Session, cid: str) -> None:
    frames = _frames(s, cid)
    pos = {f.id: i for i, f in enumerate(frames)}
    lines = list(s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)))
    lines.sort(key=lambda d: (pos.get(d.source_frame_id, 10**9), d.line_no))
    for n, d in enumerate(lines, 1):
        d.order = n
        if not d.anchor_locked and d.source_frame_id in pos:
            d.anchor_frame_id = compute_anchor(frames, pos[d.source_frame_id], d.belongs_to)
        s.add(d)


# ===========================================================================
# DIALOGUE (polish)
# ===========================================================================
def _polish_targets(s: Session, cid: str) -> list[DialogueLine]:
    return [
        d
        for d in s.exec(
            select(DialogueLine).where(DialogueLine.chapter_id == cid).order_by(DialogueLine.order)
        )
        if d.kind in POLISHABLE_KINDS and d.edited_by != "user"
    ]


def dialogue_units(cid: str) -> list[list[str]]:
    with _session() as s:
        ids = [d.id for d in _polish_targets(s, cid)]
    return [ids[i : i + DIALOGUE_CHUNK] for i in range(0, len(ids), DIALOGUE_CHUNK)]


def _speaker_name(d: DialogueLine, names: dict[str, str]) -> str:
    if d.speaker_key:
        return names.get(d.speaker_key, d.speaker_key)
    return d.speaker_label or ("(dẫn truyện)" if d.kind == "narration" else "(không rõ)")


def build_dialogue_request(cid: str, unit_index: int) -> tuple[ProviderRequest, list[str]]:
    targets = dialogue_units(cid)[unit_index]
    with _session() as s:
        ch = _chapter(s, cid)
        chars = _characters(s, ch.project_id)
        names = {c.key: c.name for c in chars}
        all_lines = list(
            s.exec(
                select(DialogueLine)
                .where(DialogueLine.chapter_id == cid)
                .order_by(DialogueLine.order)
            )
        )
        by_id = {d.id: d for d in all_lines}
        first_order = by_id[targets[0]].order
        ctx = [d for d in all_lines if d.order < first_order and d.kind != "sfx"][
            -DIALOGUE_CONTEXT:
        ]
        locked = [d for d in all_lines if d.edited_by == "user"][:60]
        rules = s.exec(
            select(AddressRule).where(
                AddressRule.project_id == ch.project_id, AddressRule.status == "approved"
            )
        ).all()
        payload = {
            "CHARACTERS": [
                {
                    "key": c.key,
                    "name": c.name,
                    "aliases": c.aliases,
                    "gender": c.gender,
                    "age_group": c.age_group,
                    "voice_style": c.voice_style,
                }
                for c in chars
                if c.status != "rejected"
            ],
            "GLOSSARY": [
                {"term": t.term, "kind": t.kind, "wrong_variants": t.variants}
                for t in approved_terms(s, ch.project_id)
            ],
            "ADDRESS_RULES": [
                {
                    "speaker": r.speaker_key,
                    "listener": r.listener_key,
                    "self": r.self_term,
                    "address": r.address_term,
                }
                for r in rules
            ],
            "CONTEXT_LINES": [{"speaker": _speaker_name(d, names), "text": d.text} for d in ctx],
            "LOCKED_LINES": [{"speaker": _speaker_name(d, names), "text": d.text} for d in locked],
            "TARGET_LINES": [
                {
                    "line_id": d.id,
                    "kind": d.kind,
                    "speaker": _speaker_name(d, names),
                    "speaker_key": d.speaker_key,
                    "speaker_gender": d.speaker_gender,
                    "text": d.text_raw,
                }
                for d in (by_id[i] for i in targets)
            ],
        }
    req = ProviderRequest(
        stage="dialogue",
        model=settings.analysis_model_text,
        system=load_prompt("dialogue", PROMPT_VERSION),
        user_text=json.dumps(payload, ensure_ascii=False, indent=1),
    )
    return req, targets


def dialogue_validator(targets: list[str]):
    expected = set(targets)

    def check(out: DialogueOut) -> None:
        ids = [line.line_id for line in out.lines]
        dup = {i for i in ids if ids.count(i) > 1}
        missing = expected - set(ids)
        extra = set(ids) - expected
        problems = []
        if missing:
            problems.append(f"missing line_id: {sorted(missing)[:20]}")
        if extra:
            problems.append(f"unknown line_id: {sorted(extra)[:20]}")
        if dup:
            problems.append(f"duplicated line_id: {sorted(dup)[:20]}")
        if problems:
            raise ValueError("; ".join(problems) + ". Return exactly one entry per TARGET line_id.")

    return check


def needs_review_for(raw: str, new: str, note: str | None) -> bool:
    if note:
        return True
    if len(raw) < 8:
        return False
    return abs(len(new) - len(raw)) / len(raw) > LENGTH_TOLERANCE


def apply_dialogue_unit(
    cid: str, unit_index: int, out: DialogueOut, *, mode: str, attempts: int, ih: str | None
) -> None:
    with _session() as s:
        ch = _chapter(s, cid)
        terms = approved_terms(s, ch.project_id)
        edits = {e.line_id: e for e in out.lines}
        for d in s.exec(select(DialogueLine).where(DialogueLine.id.in_(list(edits)))):
            if d.edited_by == "user":
                continue  # never overwrite a manual edit
            e = edits[d.id]
            new = apply_glossary(e.text.strip(), terms)
            d.text = new
            d.edited_by = "ai" if new != d.text_raw else "none"
            d.edit_note = e.edit_note
            d.needs_review = d.needs_review or needs_review_for(d.text_raw, new, e.edit_note)
            d.reviewed = False
            s.add(d)
        merge_glossary_candidates(s, ch.project_id, cid, out.glossary_candidates)
        merge_address_candidates(s, ch.project_id, out.address_candidates)
        _upsert_run(
            s, cid, "dialogue", unit_index, mode=mode, status="succeeded", attempts=attempts, ih=ih
        )
        s.commit()


def finalize_dialogue(cid: str) -> None:
    _set_status(cid, "dialogue_draft")


# ===========================================================================
# Manual mode (SPEC §4.2)
# ===========================================================================
STAGES = {
    "read": (
        read_units,
        build_read_request,
        read_validator,
        ReadBatchOut,
        apply_read_unit,
        finalize_read,
    ),
    "dialogue": (
        dialogue_units,
        build_dialogue_request,
        dialogue_validator,
        DialogueOut,
        apply_dialogue_unit,
        finalize_dialogue,
    ),
}


def prepare_manual(cid: str, stage: str) -> list[dict[str, Any]]:
    units_fn = STAGES[stage][0]
    if stage == "read":
        reset_dialogue(cid)
    units = units_fn(cid)
    if not units:
        raise AppError("NOTHING_TO_ANALYZE", "Không có gì để phân tích ở bước này", status_code=409)
    with _session() as s:
        for r in s.exec(
            select(AnalysisRun).where(AnalysisRun.chapter_id == cid, AnalysisRun.stage == stage)
        ):
            s.delete(r)
        s.flush()
        for i, targets in enumerate(units):
            _upsert_run(
                s,
                cid,
                stage,
                i,
                mode="manual",
                status="awaiting_paste",
                attempts=0,
                ih=None,
                payload={"targets": targets},
            )
        s.commit()
    return list_units(cid, stage)


def list_units(cid: str, stage: str) -> list[dict[str, Any]]:
    with _session() as s:
        runs = s.exec(
            select(AnalysisRun)
            .where(AnalysisRun.chapter_id == cid, AnalysisRun.stage == stage)
            .order_by(AnalysisRun.unit_index)
        ).all()
        return [
            {
                "id": r.id,
                "stage": r.stage,
                "unit_index": r.unit_index,
                "mode": r.mode,
                "status": r.status,
                "error": r.error,
                "size": len((r.payload or {}).get("targets", [])),
            }
            for r in runs
        ]


MANUAL_README = (
    "Giải nén (Extract All) trước khi kéo ảnh vào Gemini — "
    "kéo thẳng từ file zip sẽ bị lỗi tải lên. Mỗi gói dùng một cuộc chat MỚI.\n"
    "HƯỚNG DẪN (chế độ thủ công):\n"
    "1. Mở https://gemini.google.com (chọn model mạnh nhất bạn có).\n"
    "2. Đính kèm TẤT CẢ ảnh trong thư mục images/ theo đúng thứ tự tên file (nếu có).\n"
    "3. Mở prompt.txt, copy toàn bộ, dán vào ô chat rồi gửi.\n"
    "4. Copy NGUYÊN câu trả lời JSON của Gemini, quay lại app → 'Dán kết quả'.\n"
)


def manual_bundle(run_id: str) -> Path:
    with _session() as s:
        run = s.get(AnalysisRun, run_id)
        if not run:
            raise AppError("RUN_NOT_FOUND", "Không tìm thấy phần việc", status_code=404)
        cid, stage, unit = run.chapter_id, run.stage, run.unit_index
        ch = _chapter(s, cid)
    req, _targets = STAGES[stage][1](cid, unit)
    out = work_dir(ch) / "manual" / f"{stage}_{unit + 1:02d}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    prompt = (
        req.system
        + "\n\n=== INPUT ===\n"
        + req.user_text
        + (
            "\n\nImages are attached in this order:\n"
            + "\n".join(f"{i + 1:02d}. {im.label}" for i, im in enumerate(req.images))
            if req.images
            else ""
        )
        + "\n\nReturn ONLY the JSON object."
    )
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("HUONG_DAN.txt", MANUAL_README)
        z.writestr("prompt.txt", prompt)
        for i, im in enumerate(req.images, 1):
            role = "TARGET" if "TARGET" in im.label else "CONTEXT"
            img_bytes = _jpeg_bytes(im.path, max_side=1600, quality=85)
            z.writestr(f"images/{i:02d}_{im.label.split()[1]}_{role}.jpg", img_bytes)
    return out


def manual_paste(run_id: str, raw: str) -> dict[str, Any]:
    with _session() as s:
        run = s.get(AnalysisRun, run_id)
        if not run:
            raise AppError("RUN_NOT_FOUND", "Không tìm thấy phần việc", status_code=404)
        cid, stage, unit = run.chapter_id, run.stage, run.unit_index
        ch = _chapter(s, cid)
    _units, build, validator, schema, apply_fn, finalize = STAGES[stage]
    _req, targets = build(cid, unit)
    raw_dir = work_dir(ch) / "raw"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / f"{stage}_manual_{unit + 1:02d}.txt").write_text(raw, encoding="utf-8")
    try:
        out = parse_and_validate(raw, schema, validator(targets))
    except ValueError as e:
        with _session() as s:
            _upsert_run(s, cid, stage, unit, status="awaiting_paste", error=str(e)[:2000])
            s.commit()
        raise AppError(
            "INVALID_OUTPUT", "Kết quả dán vào chưa đúng định dạng", {"error": str(e)[:2000]}, 422
        )
    apply_fn(cid, unit, out, mode="manual", attempts=1, ih=None)
    units = list_units(cid, stage)
    if all(u["status"] == "succeeded" for u in units):
        finalize(cid)
    return {"units": units}
