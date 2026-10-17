"""Phase 2a: dialogue script, glossary, address rules, characters (SPEC §4.5, §5.1b-c, §5.2)."""

import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app import db
from app.analysis import stages
from app.analysis.glossary import apply_glossary, approved_terms, norm
from app.errors import AppError
from app.jobs.event_bus import event_bus
from app.models.analysis import (
    AddressRule,
    AnalysisRun,
    Character,
    CharacterOutfit,
    DialogueLine,
    GlossaryTerm,
)
from app.models.project import Chapter, Frame, Project
from app.services.studio import _assert_chapter_idle, active_chapter_job

FRAME_TYPES = ("scene", "dialogue_only", "caption", "sfx_only", "credit")


def _session() -> Session:
    return Session(db.engine)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _chapter(s: Session, cid: str) -> Chapter:
    ch = s.get(Chapter, cid)
    if not ch:
        raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
    return ch


def _project(s: Session, pid: str) -> Project:
    p = s.get(Project, pid)
    if not p:
        raise AppError("PROJECT_NOT_FOUND", "Không tìm thấy dự án", status_code=404)
    return p


def _emit(ch: Chapter) -> None:
    event_bus.publish_threadsafe(
        "chapter.updated", {"id": ch.id, "project_id": ch.project_id, "status": ch.status}
    )


def _touch_draft(s: Session, ch: Chapter) -> None:
    """Any edit after approval re-opens the script for review."""
    if ch.status == "dialogue_approved":
        ch.status = "dialogue_draft"
    ch.updated_at = _now()
    s.add(ch)


def _editable(s: Session, cid: str) -> Chapter:
    ch = _chapter(s, cid)
    _assert_chapter_idle(s, cid)
    if ch.status not in ("dialogue_draft", "dialogue_approved"):
        raise AppError(
            "DIALOGUE_NOT_READY",
            "Chưa có kịch bản thoại — hãy chạy phân tích trước",
            status_code=409,
        )
    return ch


def line_dict(d: DialogueLine) -> dict[str, Any]:
    return d.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Script view
# ---------------------------------------------------------------------------
def get_dialogue(cid: str) -> dict[str, Any]:
    with _session() as s:
        ch = _chapter(s, cid)
        frames = s.exec(select(Frame).where(Frame.chapter_id == cid).order_by(Frame.idx)).all()
        lines = s.exec(
            select(DialogueLine).where(DialogueLine.chapter_id == cid).order_by(DialogueLine.order)
        ).all()
        chars = s.exec(
            select(Character).where(Character.project_id == ch.project_id).order_by(Character.name)
        ).all()
        runs = s.exec(select(AnalysisRun).where(AnalysisRun.chapter_id == cid)).all()
        busy = active_chapter_job(s, cid)
        pending_review = sum(1 for d in lines if d.needs_review and not d.reviewed)
        all_frames = stages._frames(s, cid)
        read_frame_ids = stages.get_read_frame_ids(s, cid)
        unread_frames = [f for f in all_frames if f.id not in read_frame_ids]
        remaining_units = stages.read_units(cid)
        succeeded_read_runs = [
            r
            for r in runs
            if r.stage == "read" and r.status == "succeeded" and (r.payload or {}).get("targets")
        ]
        total_units = len(succeeded_read_runs) + len(remaining_units)
        succeeded_units = len(succeeded_read_runs)

        read_progress = {
            "succeeded": succeeded_units,
            "total": total_units,
            "unread_frames": len(unread_frames),
            "total_frames": len(all_frames),
            "remaining_units": len(remaining_units),
        }
        return {
            "chapter_id": cid,
            "project_id": ch.project_id,
            "status": ch.status,
            "busy_job_id": busy,
            "read_progress": read_progress,
            "frames": [
                {
                    "id": f.id,
                    "idx": f.idx,
                    "frame_type": f.frame_type,
                    "frame_type_source": f.frame_type_source,
                    "description": (f.reading or {}).get("description", ""),
                    "image_url": f"/api/assets/{f.asset_id}/file",
                }
                for f in frames
            ],
            "lines": [line_dict(d) for d in lines],
            "characters": [c.model_dump(mode="json") for c in chars if c.status != "rejected"],
            "stats": {
                "lines": len(lines),
                "pending_review": pending_review,
                "edited_ai": sum(1 for d in lines if d.edited_by == "ai"),
                "edited_user": sum(1 for d in lines if d.edited_by == "user"),
            },
            "units": {
                st: sorted(
                    [
                        {
                            "unit_index": r.unit_index,
                            "mode": r.mode,
                            "status": r.status,
                            "error": r.error,
                        }
                        for r in runs
                        if r.stage == st
                    ],
                    key=lambda u: u["unit_index"],
                )
                for st in ("read", "dialogue")
            },
        }


def update_line(lid: str, patch: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        d = s.get(DialogueLine, lid)
        if not d:
            raise AppError("LINE_NOT_FOUND", "Không tìm thấy câu thoại", status_code=404)
        ch = _editable(s, d.chapter_id)
        if "text" in patch and patch["text"] is not None:
            text = patch["text"].strip()
            if not text:
                raise AppError(
                    "VALIDATION_FAILED", "Câu thoại không được để trống", status_code=422
                )
            if text != d.text:
                d.text = text
                d.edited_by = "user"
        if "speaker_key" in patch:
            key = patch["speaker_key"] or None
            if (
                key
                and not s.exec(
                    select(Character).where(
                        Character.project_id == ch.project_id, Character.key == key
                    )
                ).first()
            ):
                raise AppError("CHARACTER_NOT_FOUND", "Không có nhân vật này", status_code=422)
            d.speaker_key = key
            if key:
                c = s.exec(
                    select(Character).where(
                        Character.project_id == ch.project_id, Character.key == key
                    )
                ).first()
                assert c
                d.speaker_gender, d.speaker_age = c.gender, c.age_group
            d.speaker_confidence = 1.0
        if "speaker_label" in patch:
            d.speaker_label = patch["speaker_label"] or None
            d.speaker_confidence = 1.0
        if patch.get("kind"):
            d.kind = patch["kind"]
        if "anchor_frame_id" in patch:
            fid = patch["anchor_frame_id"]
            if fid is None:
                d.anchor_locked = False
                stages.recompute_anchors(s, d.chapter_id)
            else:
                f = s.get(Frame, fid)
                if not f or f.chapter_id != d.chapter_id:
                    raise AppError(
                        "FRAME_NOT_FOUND", "Khung không thuộc chapter này", status_code=422
                    )
                d.anchor_frame_id = fid
                d.anchor_locked = True
        if "reviewed" in patch and patch["reviewed"] is not None:
            d.reviewed = bool(patch["reviewed"])
        elif any(k in patch for k in ("text", "speaker_key", "speaker_label", "kind")):
            d.reviewed = True  # the user looked at it and changed it
        s.add(d)
        _touch_draft(s, ch)
        s.commit()
        s.refresh(d)
        s.refresh(ch)
        _emit(ch)
        return line_dict(d)


def revert_line(lid: str) -> dict[str, Any]:
    with _session() as s:
        d = s.get(DialogueLine, lid)
        if not d:
            raise AppError("LINE_NOT_FOUND", "Không tìm thấy câu thoại", status_code=404)
        ch = _editable(s, d.chapter_id)
        d.text = d.text_raw
        d.edited_by = "none"
        d.edit_note = None
        s.add(d)
        _touch_draft(s, ch)
        s.commit()
        s.refresh(d)
        return line_dict(d)


def review_all(cid: str) -> dict[str, Any]:
    with _session() as s:
        ch = _editable(s, cid)
        n = 0
        for d in s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)):
            if d.needs_review and not d.reviewed:
                d.reviewed = True
                s.add(d)
                n += 1
        _touch_draft(s, ch)
        s.commit()
    return {"reviewed": n}


def approve_dialogue(cid: str) -> dict[str, Any]:
    with _session() as s:
        ch = _editable(s, cid)
        lines = s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)).all()
        pending = [d.id for d in lines if d.needs_review and not d.reviewed]
        if pending:
            raise AppError(
                "REVIEW_PENDING",
                f"Còn {len(pending)} câu cần soát chưa xem",
                {"line_ids": pending[:50]},
                status_code=409,
            )
        ch.status = "dialogue_approved"
        ch.updated_at = _now()
        s.add(ch)
        s.commit()
        s.refresh(ch)
        _emit(ch)
        return {"status": ch.status, "lines": len(lines)}


def reapply_glossary(cid: str) -> dict[str, Any]:
    """Re-run the deterministic glossary replacement on every non-manual line."""
    with _session() as s:
        ch = _editable(s, cid)
        terms = approved_terms(s, ch.project_id)
        n = 0
        for d in s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)):
            if d.edited_by == "user" or d.kind == "sfx":
                continue
            new = apply_glossary(d.text, terms)
            if new != d.text:
                d.text = new
                d.edited_by = "ai" if new != d.text_raw else "none"
                s.add(d)
                n += 1
        if n:
            _touch_draft(s, ch)
        s.commit()
    return {"changed": n}


def set_frame_type(fid: str, frame_type: str) -> dict[str, Any]:
    if frame_type not in FRAME_TYPES:
        raise AppError("VALIDATION_FAILED", "Loại khung không hợp lệ", status_code=422)
    with _session() as s:
        f = s.get(Frame, fid)
        if not f:
            raise AppError("FRAME_NOT_FOUND", "Không tìm thấy khung", status_code=404)
        ch = _chapter(s, f.chapter_id)
        _assert_chapter_idle(s, ch.id)
        f.frame_type = frame_type
        f.frame_type_source = "user"
        s.add(f)
        s.flush()
        stages.recompute_anchors(s, ch.id)
        _touch_draft(s, ch)
        s.commit()
        s.refresh(ch)
        _emit(ch)
        return {"id": f.id, "frame_type": f.frame_type, "frame_type_source": f.frame_type_source}


# ---------------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------------
def _clean_variants(term: str, variants: list[str]) -> list[str]:
    out: dict[str, str] = {}
    for v in variants:
        v = v.strip()
        if v and norm(v) != norm(term):
            out.setdefault(norm(v), v)
    return list(out.values())


def list_glossary(pid: str) -> list[dict[str, Any]]:
    with _session() as s:
        _project(s, pid)
        rows = s.exec(select(GlossaryTerm).where(GlossaryTerm.project_id == pid)).all()
        order = {"suggested": 0, "approved": 1, "rejected": 2}
        rows = sorted(rows, key=lambda t: (order.get(t.status, 3), norm(t.term)))
        return [t.model_dump(mode="json") for t in rows]


def _check_term_unique(s: Session, pid: str, term: str, exclude: str | None = None) -> None:
    for t in s.exec(select(GlossaryTerm).where(GlossaryTerm.project_id == pid)):
        if t.id != exclude and norm(t.term) == norm(term) and t.status != "rejected":
            raise AppError("DUPLICATE_TERM", f"Thuật ngữ '{t.term}' đã có", {"id": t.id}, 409)


def create_term(pid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        _project(s, pid)
        term = data["term"].strip()
        _check_term_unique(s, pid, term)
        t = GlossaryTerm(
            project_id=pid,
            term=term,
            kind=data.get("kind") or "other",
            variants=_clean_variants(term, data.get("variants") or []),
            note=data.get("note"),
            status=data.get("status") or "approved",
        )
        s.add(t)
        s.commit()
        s.refresh(t)
        return t.model_dump(mode="json")


def update_term(tid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        t = s.get(GlossaryTerm, tid)
        if not t:
            raise AppError("TERM_NOT_FOUND", "Không tìm thấy thuật ngữ", status_code=404)
        if data.get("term"):
            _check_term_unique(s, t.project_id, data["term"].strip(), exclude=t.id)
            t.term = data["term"].strip()
        for k in ("kind", "note", "status"):
            if k in data and data[k] is not None:
                setattr(t, k, data[k])
        if data.get("variants") is not None:
            t.variants = _clean_variants(t.term, data["variants"])
        else:
            t.variants = _clean_variants(t.term, t.variants)
        s.add(t)
        s.commit()
        s.refresh(t)
        return t.model_dump(mode="json")


def delete_term(tid: str) -> dict[str, Any]:
    with _session() as s:
        t = s.get(GlossaryTerm, tid)
        if not t:
            raise AppError("TERM_NOT_FOUND", "Không tìm thấy thuật ngữ", status_code=404)
        s.delete(t)
        s.commit()
    return {"deleted": tid}


def merge_term(tid: str, into_id: str) -> dict[str, Any]:
    """`tid` is a wrong spelling of `into_id`: its term + variants become variants of the target."""
    with _session() as s:
        src, dst = s.get(GlossaryTerm, tid), s.get(GlossaryTerm, into_id)
        if not src or not dst or src.project_id != dst.project_id or src.id == dst.id:
            raise AppError("TERM_NOT_FOUND", "Không gộp được hai thuật ngữ này", status_code=422)
        dst.variants = _clean_variants(dst.term, [*dst.variants, src.term, *src.variants])
        s.add(dst)
        s.delete(src)
        s.commit()
        s.refresh(dst)
        return dst.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Address rules
# ---------------------------------------------------------------------------
def list_address_rules(pid: str) -> list[dict[str, Any]]:
    with _session() as s:
        _project(s, pid)
        rows = s.exec(select(AddressRule).where(AddressRule.project_id == pid)).all()
        return [
            r.model_dump(mode="json")
            for r in sorted(rows, key=lambda r: (r.speaker_key, r.listener_key))
        ]


def create_address_rule(pid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        _project(s, pid)
        if data["speaker_key"] == data["listener_key"]:
            raise AppError(
                "VALIDATION_FAILED", "Người nói và người nghe phải khác nhau", status_code=422
            )
        dup = s.exec(
            select(AddressRule).where(
                AddressRule.project_id == pid,
                AddressRule.speaker_key == data["speaker_key"],
                AddressRule.listener_key == data["listener_key"],
            )
        ).first()
        if dup:
            raise AppError("DUPLICATE_RULE", "Cặp xưng hô này đã có", {"id": dup.id}, 409)
        r = AddressRule(
            project_id=pid,
            status=data.get("status") or "approved",
            **{k: data[k] for k in ("speaker_key", "listener_key", "self_term", "address_term")},
            note=data.get("note"),
        )
        s.add(r)
        s.commit()
        s.refresh(r)
        return r.model_dump(mode="json")


def update_address_rule(rid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        r = s.get(AddressRule, rid)
        if not r:
            raise AppError("RULE_NOT_FOUND", "Không tìm thấy quy tắc xưng hô", status_code=404)
        for k in ("self_term", "address_term", "note", "status"):
            if k in data and data[k] is not None:
                setattr(r, k, data[k])
        s.add(r)
        s.commit()
        s.refresh(r)
        return r.model_dump(mode="json")


def delete_address_rule(rid: str) -> dict[str, Any]:
    with _session() as s:
        r = s.get(AddressRule, rid)
        if not r:
            raise AppError("RULE_NOT_FOUND", "Không tìm thấy quy tắc xưng hô", status_code=404)
        s.delete(r)
        s.commit()
    return {"deleted": rid}


# ---------------------------------------------------------------------------
# Characters
# ---------------------------------------------------------------------------
def slug_key(name: str) -> str:
    import unicodedata

    base = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    base = "".join(c for c in base if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "nv"


def list_characters(pid: str) -> list[dict[str, Any]]:
    with _session() as s:
        _project(s, pid)
        rows = s.exec(select(Character).where(Character.project_id == pid)).all()
        counts: dict[str, int] = {}
        chapter_ids = [c.id for c in s.exec(select(Chapter).where(Chapter.project_id == pid))]
        if chapter_ids:
            for d in s.exec(select(DialogueLine).where(DialogueLine.chapter_id.in_(chapter_ids))):
                if d.speaker_key:
                    counts[d.speaker_key] = counts.get(d.speaker_key, 0) + 1
        return [
            {**c.model_dump(mode="json"), "line_count": counts.get(c.key, 0)}
            for c in sorted(rows, key=lambda c: (c.status != "suggested", c.name.casefold()))
        ]


def create_character(pid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        _project(s, pid)
        key = data.get("key") or slug_key(data["name"])
        existing = {c.key for c in s.exec(select(Character).where(Character.project_id == pid))}
        base, n = key, 2
        while key in existing:
            key = f"{base}_{n}"
            n += 1
        c = Character(
            project_id=pid,
            key=key,
            name=data["name"].strip(),
            aliases=[a.strip() for a in data.get("aliases") or [] if a.strip()],
            gender=data.get("gender") or "unknown",
            age_group=data.get("age_group") or "unknown",
            voice_style=data.get("voice_style"),
            look_lock=data.get("look_lock"),
            height_class=data.get("height_class") or "average",
            ref_frame_ids=data.get("ref_frame_ids") or [],
            look_status=data.get("look_status") or "draft",
            status=data.get("status") or "approved",
        )
        s.add(c)
        s.flush()
        default_outfit = CharacterOutfit(
            character_id=c.id,
            key="default",
            name_vi="Mặc định",
            outfit_lock="",
            short_id="",
            is_default=True,
            sheet_status="missing",
        )
        s.add(default_outfit)
        s.commit()
        s.refresh(c)
        return c.model_dump(mode="json")


def update_character(chid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        c = s.get(Character, chid)
        if not c:
            raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)
        for k in (
            "name",
            "gender",
            "age_group",
            "voice_style",
            "status",
            "look_lock",
            "height_class",
            "look_status",
        ):
            if k in data and data[k] is not None:
                setattr(c, k, data[k].strip() if isinstance(data[k], str) else data[k])
        if data.get("aliases") is not None:
            c.aliases = [a.strip() for a in data["aliases"] if a.strip()]
        if data.get("ref_frame_ids") is not None:
            c.ref_frame_ids = list(data["ref_frame_ids"])
        s.add(c)
        s.commit()
        s.refresh(c)
        return c.model_dump(mode="json")


def _project_lines(s: Session, pid: str, key: str) -> list[DialogueLine]:
    chapter_ids = [c.id for c in s.exec(select(Chapter).where(Chapter.project_id == pid))]
    if not chapter_ids:
        return []
    return list(
        s.exec(
            select(DialogueLine).where(
                DialogueLine.chapter_id.in_(chapter_ids), DialogueLine.speaker_key == key
            )
        )
    )


def delete_character(chid: str) -> dict[str, Any]:
    """Lines spoken by the character keep its name as a free-text label."""
    with _session() as s:
        c = s.get(Character, chid)
        if not c:
            raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)
        for d in _project_lines(s, c.project_id, c.key):
            d.speaker_key = None
            d.speaker_label = d.speaker_label or c.name
            s.add(d)
        for o in s.exec(select(CharacterOutfit).where(CharacterOutfit.character_id == c.id)).all():
            s.delete(o)
        s.flush()
        s.delete(c)
        s.commit()
    return {"deleted": chid}


def merge_character(chid: str, into_id: str) -> dict[str, Any]:
    """Same person detected twice → move lines, address rules and aliases into `into_id`."""
    with _session() as s:
        src, dst = s.get(Character, chid), s.get(Character, into_id)
        if not src or not dst or src.project_id != dst.project_id or src.id == dst.id:
            raise AppError(
                "CHARACTER_NOT_FOUND", "Không gộp được hai nhân vật này", status_code=422
            )
        for d in _project_lines(s, src.project_id, src.key):
            d.speaker_key = dst.key
            s.add(d)
        for r in s.exec(select(AddressRule).where(AddressRule.project_id == src.project_id)):
            if r.speaker_key == src.key:
                r.speaker_key = dst.key
            if r.listener_key == src.key:
                r.listener_key = dst.key
            s.add(r)
        known = {norm(x) for x in [dst.name, *dst.aliases]}
        dst.aliases = [*dst.aliases, *[a for a in [src.name, *src.aliases] if norm(a) not in known]]
        if dst.gender == "unknown":
            dst.gender = src.gender
        if dst.age_group == "unknown":
            dst.age_group = src.age_group
        s.add(dst)

        # Move outfits of src to dst (avoid duplicate keys, preserve sheets, only 1 default)
        src_outfits = s.exec(
            select(CharacterOutfit).where(CharacterOutfit.character_id == src.id)
        ).all()
        dst_outfits = s.exec(
            select(CharacterOutfit).where(CharacterOutfit.character_id == dst.id)
        ).all()
        taken_keys = {o.key for o in dst_outfits}

        for o in src_outfits:
            if o.key in taken_keys:
                base_cand = f"{src.key}_{o.key}"
                cand = base_cand
                counter = 2
                while cand in taken_keys:
                    cand = f"{base_cand}_{counter}"
                    counter += 1
                o.key = cand
            taken_keys.add(o.key)
            o.character_id = dst.id
            o.is_default = False
            s.add(o)

        # Ensure dst has exactly 1 default outfit
        has_default = any(o.is_default for o in dst_outfits)
        if not has_default and (dst_outfits or src_outfits):
            first_outfit = dst_outfits[0] if dst_outfits else src_outfits[0]
            first_outfit.is_default = True
            s.add(first_outfit)
        elif has_default:
            first_def = True
            for o in dst_outfits:
                if o.is_default:
                    if first_def:
                        first_def = False
                    else:
                        o.is_default = False
                        s.add(o)

        s.flush()
        s.delete(src)
        s.commit()
        s.refresh(dst)
        return dst.model_dump(mode="json")
