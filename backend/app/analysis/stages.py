"""Phase 2a analysis stages: `read` (frame types + raw dialogue + speakers) and `dialogue` (polish).

Both stages are split into UNITS (a batch of frames / a chunk of lines). A unit can be produced
by the API provider (job) or pasted by the user (manual mode) — both go through the same
`apply_*_unit` + finalize code, so results are identical (SPEC §4.2).
"""

import json
import shutil
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
def get_read_frame_ids(s: Session, cid: str) -> set[str]:
    """Return frame IDs that are in targets of an AnalysisRun read succeeded (with output)."""
    runs = s.exec(
        select(AnalysisRun).where(
            AnalysisRun.chapter_id == cid,
            AnalysisRun.stage == "read",
            AnalysisRun.status == "succeeded",
        )
    ).all()
    read_ids: set[str] = set()
    for r in runs:
        if (r.payload or {}).get("output"):
            for fid in (r.payload or {}).get("targets", []):
                read_ids.add(fid)
    return read_ids


def read_units(cid: str) -> list[list[str]]:
    with _session() as s:
        frames = _frames(s, cid)
        if not frames:
            return []
        read_ids = get_read_frame_ids(s, cid)
        unread = [f for f in frames if f.id not in read_ids]
        if not unread:
            return []
        batch_size = max(4, min(12, getattr(settings, "read_batch_size", 6)))
        return [
            [f.id for f in unread[i : i + batch_size]] for i in range(0, len(unread), batch_size)
        ]


def reset_dialogue(cid: str) -> int:
    """Start a fresh read: back up existing lines, then delete them and old runs."""
    with _session() as s:
        ch = _chapter(s, cid)
        cache = work_dir(ch) / "cache"
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
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


def build_read_request(
    cid: str, unit_index: int, targets: list[str] | None = None
) -> tuple[ProviderRequest, list[str]]:
    with _session() as s:
        ch = _chapter(s, cid)
        frames = _frames(s, cid)
        ids = [f.id for f in frames]
        if targets is None:
            units = read_units(cid)
            targets = units[unit_index]
        first, last = ids.index(targets[0]), ids.index(targets[-1])
        ctx_prev = frames[first - 1] if first > 0 else None
        ctx_next = frames[last + 1] if last + 1 < len(frames) else None
        by_id = {f.id: f for f in frames}

        def img(f: Frame, role: str) -> ImagePart:
            a = s.get(Asset, f.asset_id)
            assert a
            return ImagePart(f"FRAME {f.id} ({role})", asset_abs_path(ch.project_id, a.path))

        images = []
        if ctx_prev and ctx_prev.id not in targets:
            images.append(img(ctx_prev, "CONTEXT — previous frame, do not return"))
        images += [img(by_id[i], "TARGET") for i in targets]
        if ctx_next and ctx_next.id not in targets:
            images.append(img(ctx_next, "CONTEXT — next frame, do not return"))

        prev_run = s.exec(
            select(AnalysisRun)
            .where(
                AnalysisRun.chapter_id == cid,
                AnalysisRun.stage == "read",
                AnalysisRun.status == "succeeded",
            )
            .order_by(AnalysisRun.unit_index.desc())
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
            "CONTEXT_FRAMES": [f.id for f in (ctx_prev, ctx_next) if f and f.id not in targets],
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
    cid: str,
    unit_index: int,
    out: ReadBatchOut,
    *,
    mode: str,
    attempts: int,
    ih: str | None,
    targets: list[str] | None = None,
) -> None:
    with _session() as s:
        ch = _chapter(s, cid)
        frames = {f.id: f for f in _frames(s, cid)}
        target_fids = targets if targets is not None else [fr.frame_id for fr in out.frames]
        for d in s.exec(select(DialogueLine).where(DialogueLine.source_frame_id.in_(target_fids))):
            s.delete(d)
        for fr in out.frames:
            if fr.frame_id not in frames:
                continue
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

        existing_runs = s.exec(
            select(AnalysisRun).where(
                AnalysisRun.chapter_id == cid,
                AnalysisRun.stage == "read",
            )
        ).all()
        matched = next(
            (r for r in existing_runs if (r.payload or {}).get("targets") == target_fids),
            None,
        )
        target_unit_index = (
            matched.unit_index
            if matched
            else (max((r.unit_index for r in existing_runs), default=-1) + 1)
        )

        _upsert_run(
            s,
            cid,
            "read",
            target_unit_index,
            mode=mode,
            status="succeeded",
            attempts=attempts,
            ih=ih,
            payload={
                "targets": target_fids,
                "summary": out.running_summary,
                "output": out.model_dump(mode="json"),
            },
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

        unread = len(read_units(cid)) > 0
        if unread:
            ch.status = "frames_approved"
        else:
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
    processed_line_ids: set[str] = set()
    for r in s.exec(
        select(AnalysisRun).where(
            AnalysisRun.chapter_id == cid,
            AnalysisRun.stage == "dialogue",
            AnalysisRun.status == "succeeded",
        )
    ):
        processed_line_ids.update((r.payload or {}).get("targets", []))

    return [
        d
        for d in s.exec(
            select(DialogueLine).where(DialogueLine.chapter_id == cid).order_by(DialogueLine.order)
        )
        if d.kind in POLISHABLE_KINDS
        and d.edited_by != "user"
        and (d.edited_by == "none" and d.id not in processed_line_ids)
    ]


def dialogue_units(cid: str) -> list[list[str]]:
    with _session() as s:
        ids = [d.id for d in _polish_targets(s, cid)]
    return [ids[i : i + DIALOGUE_CHUNK] for i in range(0, len(ids), DIALOGUE_CHUNK)]


def _speaker_name(d: DialogueLine, names: dict[str, str]) -> str:
    if d.speaker_key:
        return names.get(d.speaker_key, d.speaker_key)
    return d.speaker_label or ("(dẫn truyện)" if d.kind == "narration" else "(không rõ)")


def build_dialogue_request(
    cid: str, unit_index: int, targets: list[str] | None = None
) -> tuple[ProviderRequest, list[str]]:
    if targets is None:
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
    cid: str,
    unit_index: int,
    out: DialogueOut,
    *,
    mode: str,
    attempts: int,
    ih: str | None,
    targets: list[str] | None = None,
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

        target_ids = targets if targets is not None else list(edits)
        existing_runs = s.exec(
            select(AnalysisRun).where(
                AnalysisRun.chapter_id == cid,
                AnalysisRun.stage == "dialogue",
            )
        ).all()
        matched = next(
            (r for r in existing_runs if (r.payload or {}).get("targets") == target_ids),
            None,
        )
        target_unit_index = (
            matched.unit_index
            if matched
            else (max((r.unit_index for r in existing_runs), default=-1) + 1)
        )

        _upsert_run(
            s,
            cid,
            "dialogue",
            target_unit_index,
            mode=mode,
            status="succeeded",
            attempts=attempts,
            ih=ih,
            payload={
                "targets": target_ids,
                "output": out.model_dump(mode="json"),
            },
        )
        s.commit()


def reset_dialogue_runs(cid: str) -> None:
    """Clear dialogue runs and reset AI edited lines to none (keep user edits)."""
    with _session() as s:
        ch = _chapter(s, cid)
        cache = work_dir(ch) / "cache"
        if cache.exists():
            shutil.rmtree(cache, ignore_errors=True)
        for r in s.exec(
            select(AnalysisRun).where(
                AnalysisRun.chapter_id == cid, AnalysisRun.stage == "dialogue"
            )
        ):
            s.delete(r)
        for d in s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)):
            if d.edited_by == "ai":
                d.edited_by = "none"
                d.text = d.text_raw
                d.edit_note = None
                s.add(d)
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


def prepare_manual(cid: str, stage: str, force_all: bool = False) -> list[dict[str, Any]]:
    units_fn = STAGES[stage][0]
    if stage == "read" and force_all:
        reset_dialogue(cid)
    elif stage == "dialogue" and force_all:
        reset_dialogue_runs(cid)
    units = units_fn(cid)
    if not units:
        raise AppError("NOTHING_TO_ANALYZE", "Không có gì để phân tích ở bước này", status_code=409)
    with _session() as s:
        if force_all:
            for r in s.exec(
                select(AnalysisRun).where(AnalysisRun.chapter_id == cid, AnalysisRun.stage == stage)
            ):
                s.delete(r)
            s.flush()
        existing_runs = list(
            s.exec(
                select(AnalysisRun).where(AnalysisRun.chapter_id == cid, AnalysisRun.stage == stage)
            ).all()
        )
        for i, targets in enumerate(units):
            matching = next(
                (r for r in existing_runs if (r.payload or {}).get("targets") == targets),
                None,
            )
            if matching and matching.status == "succeeded":
                continue
            unit_idx = (
                matching.unit_index
                if matching
                else (max((r.unit_index for r in existing_runs), default=-1) + 1)
            )
            run = _upsert_run(
                s,
                cid,
                stage,
                unit_idx,
                mode="manual",
                status="awaiting_paste",
                attempts=0,
                ih=None,
                payload={"targets": targets},
            )
            if not matching:
                existing_runs.append(run)
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
        targets = (run.payload or {}).get("targets")
    req, _targets = STAGES[stage][1](cid, unit, targets=targets)
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
        targets = (run.payload or {}).get("targets")
    _units, build, validator, schema, apply_fn, finalize = STAGES[stage]
    _req, targets = build(cid, unit, targets=targets)
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
    apply_fn(cid, unit, out, mode="manual", attempts=1, ih=None, targets=targets)
    units = list_units(cid, stage)
    if all(u["status"] == "succeeded" for u in units):
        finalize(cid)
    return {"units": units}
