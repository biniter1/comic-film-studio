"""Phase 2c stages: `plan` (split the chapter into scenes, text only) and `shots` (one unit per
scene: storyboard fields per shot). Plugged into stages.STAGES so jobs, manual mode, skip-if-done
and paste all work exactly like `read`/`dialogue` (SPEC §4.1, §4.6, §5.3)."""

import json
from typing import Any

from sqlmodel import Session, select

from app import db
from app.analysis import shot_rules as R
from app.analysis.engine import load_prompt
from app.analysis.schemas import PlanOut, ShotsOut
from app.config import settings
from app.errors import AppError
from app.jobs.event_bus import event_bus
from app.models.analysis import AnalysisRun, Character, CharacterOutfit, DialogueLine, Location
from app.models.project import Asset, Chapter, Frame, Project
from app.models.shots import Scene, Shot
from app.providers.base import ImagePart, ProviderRequest
from app.storage import asset_abs_path

PROMPT_VERSION_PLAN = "v1"
PROMPT_VERSION_SHOTS = "v1"
MAX_SCENE_FRAMES = 12
PLANNABLE = ("dialogue_approved", "shots_draft", "plan_approved")
SPOKEN = ("dialogue", "inner_thought", "narration")


def _session() -> Session:
    return Session(db.engine)


def _chapter(s: Session, cid: str) -> Chapter:
    ch = s.get(Chapter, cid)
    if not ch:
        raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
    return ch


def _emit(ch: Chapter) -> None:
    event_bus.publish_threadsafe(
        "chapter.updated", {"id": ch.id, "project_id": ch.project_id, "status": ch.status}
    )


def assert_plannable(cid: str) -> Chapter:
    with _session() as s:
        ch = _chapter(s, cid)
        if ch.status not in PLANNABLE:
            raise AppError(
                "DIALOGUE_NOT_APPROVED",
                "Hãy duyệt kịch bản thoại trước khi lập kế hoạch shot",
                status_code=409,
            )
        return ch


def _frames(s: Session, cid: str) -> list[Frame]:
    return list(s.exec(select(Frame).where(Frame.chapter_id == cid).order_by(Frame.idx)))


def _scene_frames(s: Session, cid: str) -> list[Frame]:
    return [f for f in _frames(s, cid) if f.frame_type in (None, "scene")]


def _lines(s: Session, cid: str) -> list[DialogueLine]:
    return list(
        s.exec(
            select(DialogueLine).where(DialogueLine.chapter_id == cid).order_by(DialogueLine.order)
        )
    )


def _speaker(d: DialogueLine, names: dict[str, str]) -> str | None:
    if d.speaker_key:
        return names.get(d.speaker_key, d.speaker_key)
    return d.speaker_label


def _characters_json(s: Session, pid: str) -> list[dict[str, Any]]:
    out = []
    for c in s.exec(select(Character).where(Character.project_id == pid)):
        if c.status == "rejected":
            continue
        outfits = s.exec(select(CharacterOutfit).where(CharacterOutfit.character_id == c.id)).all()
        out.append(
            {
                "key": c.key,
                "name": c.name,
                "role": c.role,
                "is_group": c.is_group,
                "gender": c.gender,
                "outfits": [o.key for o in outfits],
                "default_outfit": next((o.key for o in outfits if o.is_default), None),
            }
        )
    return out


def _locations_json(s: Session, pid: str) -> list[dict[str, Any]]:
    return [
        {"key": loc.key, "name_vi": loc.name_vi, "location_lock": loc.location_lock}
        for loc in s.exec(select(Location).where(Location.project_id == pid))
    ]


# ===========================================================================
# PLAN
# ===========================================================================
def plan_units(cid: str) -> list[list[str]]:
    with _session() as s:
        ids = [f.id for f in _scene_frames(s, cid)]
    return [ids] if ids else []


def build_plan_request(
    cid: str, unit_index: int, targets: list[str] | None = None
) -> tuple[ProviderRequest, list[str]]:
    with _session() as s:
        ch = _chapter(s, cid)
        frames = _frames(s, cid)
        names = {
            c.key: c.name
            for c in s.exec(select(Character).where(Character.project_id == ch.project_id))
        }
        by_anchor: dict[str, list[dict[str, Any]]] = {}
        for d in _lines(s, cid):
            if d.anchor_frame_id:
                by_anchor.setdefault(d.anchor_frame_id, []).append(
                    {"speaker": _speaker(d, names), "kind": d.kind, "text": d.text}
                )
        scene_ids = [f.id for f in frames if f.frame_type in (None, "scene")]
        targets = targets or scene_ids
        payload = {
            "SCENE_FRAMES": [
                {
                    "frame_id": f.id,
                    "idx": f.idx,
                    "description": (f.reading or {}).get("description", ""),
                    "characters": (f.reading or {}).get("characters", []),
                    "intensity": (f.reading or {}).get("intensity"),
                    "continues_previous": (f.reading or {}).get("continues_previous"),
                    "technique_hint": (f.reading or {}).get("technique_hint"),
                    "lines": by_anchor.get(f.id, []),
                }
                for f in frames
                if f.id in targets
            ],
            "KNOWN_LOCATIONS": _locations_json(s, ch.project_id),
            "CHARACTERS": [
                {"key": c["key"], "name": c["name"], "role": c["role"]}
                for c in _characters_json(s, ch.project_id)
            ],
            "MAX_FRAMES_PER_SCENE": MAX_SCENE_FRAMES,
        }
    req = ProviderRequest(
        stage="plan",
        model=settings.analysis_model_text,
        system=load_prompt("plan", PROMPT_VERSION_PLAN),
        user_text=json.dumps(payload, ensure_ascii=False, indent=1),
    )
    return req, targets


def plan_validator(targets: list[str]):
    def check(out: PlanOut) -> None:
        flat = [fid for sc in out.scenes for fid in sc.frame_ids]
        if flat != targets:
            missing = [f for f in targets if f not in flat]
            extra = [f for f in flat if f not in targets]
            raise ValueError(
                "Concatenating scenes[].frame_ids must give EXACTLY the SCENE_FRAMES ids in "
                f"order, each once. Missing: {missing[:20]}; unknown/duplicated: {extra[:20]}."
            )
        big = [i for i, sc in enumerate(out.scenes) if len(sc.frame_ids) > MAX_SCENE_FRAMES]
        if big:
            raise ValueError(f"Scenes {big} have more than {MAX_SCENE_FRAMES} frames — split them.")

    return check


def _upsert_run(s: Session, cid: str, stage: str, unit_index: int, **kw: Any) -> None:
    from app.analysis.stages import _upsert_run as up

    up(s, cid, stage, unit_index, **kw)


def apply_plan_unit(
    cid: str,
    unit_index: int,
    out: PlanOut,
    *,
    mode: str,
    attempts: int,
    ih: str | None,
    targets: list[str] | None = None,
) -> None:
    with _session() as s:
        ch = _chapter(s, cid)
        known_locs = {
            loc.key for loc in s.exec(select(Location).where(Location.project_id == ch.project_id))
        }
        for nl in out.new_locations:
            if nl.key not in known_locs:
                s.add(
                    Location(
                        project_id=ch.project_id,
                        key=nl.key,
                        name_vi=nl.name_vi,
                        location_lock=nl.location_lock,
                    )
                )
                known_locs.add(nl.key)
        old = {
            tuple(sc.frame_ids): sc for sc in s.exec(select(Scene).where(Scene.chapter_id == cid))
        }
        keep_ids: set[str] = set()
        for i, draft in enumerate(out.scenes, 1):
            sc = old.get(tuple(draft.frame_ids))
            if sc is None:
                sc = Scene(chapter_id=cid, code="", order=i, frame_ids=list(draft.frame_ids))
            sc.code, sc.order = f"SC{i:02d}", i
            sc.summary = draft.summary
            sc.location_key = draft.location_key if draft.location_key in known_locs else None
            sc.mood = draft.mood
            s.add(sc)
            s.flush()
            keep_ids.add(sc.id)
        for sc in old.values():
            if sc.id not in keep_ids:
                for sh in s.exec(select(Shot).where(Shot.scene_id == sc.id)):
                    s.delete(sh)
                s.flush()
                s.delete(sc)
        # shots runs of scenes that no longer exist are obsolete
        kept_targets = [
            list(sc.frame_ids) for sc in s.exec(select(Scene).where(Scene.chapter_id == cid))
        ]
        for r in s.exec(
            select(AnalysisRun).where(AnalysisRun.chapter_id == cid, AnalysisRun.stage == "shots")
        ):
            if (r.payload or {}).get("targets") not in kept_targets:
                s.delete(r)
        _upsert_run(
            s,
            cid,
            "plan",
            unit_index,
            mode=mode,
            status="succeeded",
            attempts=attempts,
            ih=ih,
            payload={"targets": targets or [], "output": out.model_dump(mode="json")},
        )
        s.commit()


def finalize_plan(cid: str) -> None:
    recompute_chapter(cid)


# ===========================================================================
# SHOTS (one unit per scene)
# ===========================================================================
def shots_units(cid: str) -> list[list[str]]:
    with _session() as s:
        scenes = s.exec(select(Scene).where(Scene.chapter_id == cid).order_by(Scene.order)).all()
        return [list(sc.frame_ids) for sc in scenes if sc.frame_ids]


def _scene_for(s: Session, cid: str, targets: list[str]) -> Scene:
    for sc in s.exec(select(Scene).where(Scene.chapter_id == cid)):
        if list(sc.frame_ids) == list(targets):
            return sc
    raise AppError("SCENE_NOT_FOUND", "Không tìm thấy scene — hãy chạy lại bước lập scene", 409)


def build_shots_request(
    cid: str, unit_index: int, targets: list[str] | None = None
) -> tuple[ProviderRequest, list[str]]:
    with _session() as s:
        ch = _chapter(s, cid)
        if targets is None:
            targets = shots_units(cid)[unit_index]
        sc = _scene_for(s, cid, targets)
        frames = {f.id: f for f in _frames(s, cid)}
        names = {
            c.key: c.name
            for c in s.exec(select(Character).where(Character.project_id == ch.project_id))
        }
        images = []
        for fid in targets:
            f = frames[fid]
            a = s.get(Asset, f.asset_id)
            assert a
            images.append(ImagePart(f"FRAME {fid} (TARGET)", asset_abs_path(ch.project_id, a.path)))
        lines = [
            {
                "line_id": d.id,
                "frame_id": d.anchor_frame_id,
                "kind": d.kind,
                "speaker": _speaker(d, names),
                "text": d.text,
            }
            for d in _lines(s, cid)
            if d.anchor_frame_id in targets
        ]
        prev = s.exec(
            select(Scene).where(Scene.chapter_id == cid, Scene.order == sc.order - 1)
        ).first()
        prev_end = ""
        if prev:
            last = s.exec(
                select(Shot).where(Shot.scene_id == prev.id).order_by(Shot.order.desc())
            ).first()
            prev_end = last.end_state if last else ""
        payload = {
            "SCENE": {
                "code": sc.code,
                "summary": sc.summary,
                "location_key": sc.location_key,
                "mood": sc.mood,
            },
            "FRAMES": [
                {
                    "frame_id": fid,
                    "description": (frames[fid].reading or {}).get("description", ""),
                    "characters": (frames[fid].reading or {}).get("characters", []),
                    "intensity": (frames[fid].reading or {}).get("intensity"),
                    "continues_previous": (frames[fid].reading or {}).get("continues_previous"),
                    "technique_hint": (frames[fid].reading or {}).get("technique_hint"),
                    "implied_motion": (frames[fid].reading or {}).get("implied_motion"),
                }
                for fid in targets
            ],
            "LINES": lines,
            "CHARACTERS": _characters_json(s, ch.project_id),
            "LOCATIONS": _locations_json(s, ch.project_id),
            "PREVIOUS_SHOT_END_STATE": prev_end or None,
            "CLIP_SECONDS": settings.muse_clip_seconds,
        }
    req = ProviderRequest(
        stage="shots",
        model=settings.analysis_model_vision,
        system=load_prompt("shots", PROMPT_VERSION_SHOTS),
        user_text=json.dumps(payload, ensure_ascii=False, indent=1),
        images=images,
    )
    return req, targets


def shots_validator(targets: list[str]):
    allowed = set(targets)

    def check(out: ShotsOut) -> None:
        unknown = sorted({f for sh in out.shots for f in sh.frame_ids if f not in allowed})
        if unknown:
            raise ValueError(
                f"shots[].frame_ids may only use the TARGET frames; unknown: {unknown}"
            )
        covered = {f for sh in out.shots for f in sh.frame_ids}
        missing = [f for f in targets if f not in covered]
        if missing:
            raise ValueError(
                f"Every TARGET frame must appear in at least one shot; missing: {missing}"
            )

    return check


def apply_shots_unit(
    cid: str,
    unit_index: int,
    out: ShotsOut,
    *,
    mode: str,
    attempts: int,
    ih: str | None,
    targets: list[str] | None = None,
) -> None:
    with _session() as s:
        if targets is None:
            targets = shots_units(cid)[unit_index]
        sc = _scene_for(s, cid, targets)
        for old in s.exec(select(Shot).where(Shot.scene_id == sc.id)):
            s.delete(old)
        s.flush()
        for i, d in enumerate(out.shots, 1):
            s.add(
                Shot(
                    chapter_id=cid,
                    scene_id=sc.id,
                    code=f"T{sc.order:02d}{i:02d}",
                    order=sc.order * 1000 + i,
                    transition_in=d.transition_in,
                    frame_ids=list(d.frame_ids),
                    inserted=d.inserted,
                    duration_s=d.duration_s,
                    camera=d.camera.model_dump(),
                    location_key=d.location_key or sc.location_key,
                    blocking=[b.model_dump() for b in d.blocking],
                    beats=[b.model_dump() for b in d.beats],
                    start_state=d.start_state,
                    end_state=d.end_state,
                    action=d.action,
                    emotion=d.emotion,
                    sfx_notes=d.sfx_notes,
                    attachments=[],
                    rule_notes=[],
                    prompt_override={},
                    titles=[],
                    line_ids=list(d.line_ids),
                )
            )
        _upsert_run(
            s,
            cid,
            "shots",
            unit_index,
            mode=mode,
            status="succeeded",
            attempts=attempts,
            ih=ih,
            payload={"targets": targets, "output": out.model_dump(mode="json")},
        )
        s.commit()
    recompute_chapter(cid, set_status=False)


def finalize_shots(cid: str) -> None:
    recompute_chapter(cid)
    with _session() as s:
        ch = _chapter(s, cid)
        if ch.status != "plan_approved":
            ch.status = "shots_draft"
            s.add(ch)
            s.commit()
            s.refresh(ch)
        _emit(ch)


# ===========================================================================
# Rules + composer over the DB
# ===========================================================================
def _ctx(s: Session, ch: Chapter) -> R.Ctx:
    proj = s.get(Project, ch.project_id)
    ps = (proj.settings_json if proj else {}) or {}
    frames = _frames(s, ch.id)
    scenes = s.exec(select(Scene).where(Scene.chapter_id == ch.id)).all()
    frame_scene = {fid: sc.id for sc in scenes for fid in sc.frame_ids}
    chars: dict[str, R.CharInfo] = {}
    for c in s.exec(select(Character).where(Character.project_id == ch.project_id)):
        if c.status == "rejected":
            continue
        outfits = s.exec(select(CharacterOutfit).where(CharacterOutfit.character_id == c.id)).all()
        chars[c.key] = R.CharInfo(
            key=c.key,
            name=c.name,
            role=c.role,
            is_group=c.is_group,
            look_lock=c.look_lock or "",
            outfits={
                o.key: {
                    "outfit_lock": o.outfit_lock or "",
                    "short_id": o.short_id or "",
                    "sheet_asset_id": o.sheet_asset_id if o.sheet_status == "approved" else None,
                }
                for o in outfits
            },
            default_outfit=next((o.key for o in outfits if o.is_default), None),
        )
    locs = {
        loc.key: R.LocInfo(
            key=loc.key,
            name=loc.name_vi,
            location_lock=loc.location_lock or "",
            sheet_asset_id=loc.sheet_asset_id if loc.sheet_status == "approved" else None,
        )
        for loc in s.exec(select(Location).where(Location.project_id == ch.project_id))
    }
    lines = {
        d.id: {
            "kind": d.kind,
            "text": d.text,
            "anchor_frame_id": d.anchor_frame_id,
            "order": d.order,
        }
        for d in _lines(s, ch.id)
    }
    return R.Ctx(
        frame_scene=frame_scene,
        frame_asset={f.id: f.asset_id for f in frames},
        frame_chars={f.id: list((f.reading or {}).get("characters", [])) for f in frames},
        lines=lines,
        chars=chars,
        locs=locs,
        style_lock=ps.get("style_lock") or R.DEFAULT_STYLE,
        negative=ps.get("negative") or R.DEFAULT_NEGATIVE,
        clip_seconds=settings.muse_clip_seconds,
        max_ref_images=int(ps.get("max_ref_images") or 4),
    )


def _shot_dict(sh: Shot, line_ids: list[str]) -> dict[str, Any]:
    return {
        "id": sh.id,
        "transition_in": sh.transition_in,
        "frame_ids": list(sh.frame_ids),
        "inserted": sh.inserted,
        "duration_s": sh.duration_s,
        "camera": dict(sh.camera),
        "location_key": sh.location_key,
        "blocking": [dict(b) for b in sh.blocking],
        "beats": [dict(b) for b in sh.beats],
        "start_state": sh.start_state,
        "end_state": sh.end_state,
        "action": sh.action,
        "line_ids": line_ids,
        "rule_notes": [],
    }


def recompute_chapter(cid: str, set_status: bool = False) -> None:
    """Re-run rules §4.3 + compose prompts §4.6 for every shot of the chapter."""
    with _session() as s:
        ch = _chapter(s, cid)
        ctx = _ctx(s, ch)
        scenes = s.exec(select(Scene).where(Scene.chapter_id == cid).order_by(Scene.order)).all()
        rows = {sh.id: sh for sh in s.exec(select(Shot).where(Shot.chapter_id == cid))}
        by_scene: dict[str, list[dict]] = {}
        for sh in sorted(rows.values(), key=lambda x: x.order):
            by_scene.setdefault(sh.scene_id, []).append(_shot_dict(sh, list(sh.line_ids)))
        flat = R.apply_rules(
            [
                {"id": sc.id, "frame_ids": list(sc.frame_ids), "location_key": sc.location_key}
                for sc in scenes
            ],
            by_scene,
            ctx,
        )
        line_shot: dict[str, str] = {}
        for d in flat:
            R.compose(d, ctx)
            sh = rows[d["id"]]
            sh.code, sh.order = d["code"], d["order"]
            sh.chain_code, sh.chain_pos = d["chain_code"], d["chain_pos"]
            sh.transition_in = d["transition_in"]
            sh.duration_s = d["duration_s"]
            sh.beats = d["beats"]
            sh.blocking = d["blocking"]
            sh.location_key = d["location_key"]
            sh.titles = d["titles"]
            sh.line_ids = d["line_ids"]
            sh.attachments = d["attachments"]
            sh.rule_notes = d["rule_notes"]
            sh.keyframe_prompt = (sh.prompt_override or {}).get("keyframe") or d["keyframe_prompt"]
            sh.video_prompt = (sh.prompt_override or {}).get("video") or d["video_prompt"]
            s.add(sh)
            for lid in d["line_ids"]:
                line_shot[lid] = sh.id
        for d in _lines(s, cid):
            new = line_shot.get(d.id)
            if d.shot_code != new:
                d.shot_code = new
                s.add(d)
        s.commit()


# ===========================================================================
# API services
# ===========================================================================
def get_shots(cid: str) -> dict[str, Any]:
    from app.services.studio import active_chapter_job

    with _session() as s:
        ch = _chapter(s, cid)
        scenes = s.exec(select(Scene).where(Scene.chapter_id == cid).order_by(Scene.order)).all()
        shots = s.exec(select(Shot).where(Shot.chapter_id == cid).order_by(Shot.order)).all()
        frames = _frames(s, cid)
        lines = {d.id: d for d in _lines(s, cid)}
        names = {
            c.key: c.name
            for c in s.exec(select(Character).where(Character.project_id == ch.project_id))
        }
        runs = s.exec(select(AnalysisRun).where(AnalysisRun.chapter_id == cid)).all()
        return {
            "chapter_id": cid,
            "project_id": ch.project_id,
            "status": ch.status,
            "busy_job_id": active_chapter_job(s, cid),
            "frames": [
                {
                    "id": f.id,
                    "idx": f.idx,
                    "frame_type": f.frame_type,
                    "image_url": f"/api/assets/{f.asset_id}/file",
                }
                for f in frames
            ],
            "scenes": [sc.model_dump(mode="json") for sc in scenes],
            "shots": [
                {
                    **sh.model_dump(mode="json"),
                    "lines": [
                        {"id": d.id, "kind": d.kind, "text": d.text, "speaker": _speaker(d, names)}
                        for d in lines.values()
                        if d.shot_code == sh.id
                    ],
                    "attachments": [
                        {**a, "url": f"/api/assets/{a['asset_id']}/file"} for a in sh.attachments
                    ],
                }
                for sh in shots
            ],
            "characters": _characters_json(s, ch.project_id),
            "locations": _locations_json(s, ch.project_id),
            "units": {
                st: sorted(
                    [
                        {
                            "unit_index": r.unit_index,
                            "status": r.status,
                            "mode": r.mode,
                            "error": r.error,
                        }
                        for r in runs
                        if r.stage == st
                    ],
                    key=lambda u: u["unit_index"],
                )
                for st in ("plan", "shots")
            },
        }


EDITABLE = (
    "transition_in",
    "duration_s",
    "camera",
    "location_key",
    "blocking",
    "beats",
    "start_state",
    "end_state",
    "action",
    "emotion",
    "sfx_notes",
)


def update_shot(sid: str, patch: dict[str, Any]) -> dict[str, Any]:
    from app.services.studio import _assert_chapter_idle

    with _session() as s:
        sh = s.get(Shot, sid)
        if not sh:
            raise AppError("SHOT_NOT_FOUND", "Không tìm thấy shot", status_code=404)
        ch = _chapter(s, sh.chapter_id)
        _assert_chapter_idle(s, ch.id)
        for k in EDITABLE:
            if k in patch and patch[k] is not None:
                setattr(sh, k, patch[k])
        if "prompt_override" in patch and patch["prompt_override"] is not None:
            po = {k: v for k, v in patch["prompt_override"].items() if v}
            sh.prompt_override = po
        sh.edited_by = "user"
        if ch.status == "plan_approved":
            ch.status = "shots_draft"
            s.add(ch)
        s.add(sh)
        s.commit()
        cid = ch.id
    recompute_chapter(cid)
    with _session() as s:
        sh2 = s.get(Shot, sid)
        assert sh2
        return sh2.model_dump(mode="json")


def approve_plan(cid: str) -> dict[str, Any]:
    with _session() as s:
        ch = _chapter(s, cid)
        shots = s.exec(select(Shot).where(Shot.chapter_id == cid)).all()
        if not shots:
            raise AppError("NO_SHOTS", "Chưa có shot nào để duyệt", status_code=409)
        ch.status = "plan_approved"
        s.add(ch)
        s.commit()
        s.refresh(ch)
        _emit(ch)
        return {"status": ch.status, "shots": len(shots)}


def reset_plan(cid: str) -> None:
    """'Lập lại toàn bộ' — forget plan + shots runs (the next run calls the AI again)."""
    with _session() as s:
        for r in s.exec(
            select(AnalysisRun).where(
                AnalysisRun.chapter_id == cid, AnalysisRun.stage.in_(["plan", "shots"])
            )
        ):
            s.delete(r)
        for sh in s.exec(select(Shot).where(Shot.chapter_id == cid)):
            s.delete(sh)
        s.flush()
        for sc in s.exec(select(Scene).where(Scene.chapter_id == cid)):
            s.delete(sc)
        s.commit()
