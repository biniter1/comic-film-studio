"""Phase 2a REST API (SPEC §9): analysis, dialogue script, glossary, address rules, characters."""

from typing import Any, Literal, Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import db
from app.analysis import stages
from app.analysis.engine import extract_json
from app.analysis.schemas import Age, FrameType, Gender, Role, TermKind, TextKind
from app.errors import AppError
from app.jobs.runner import job_service
from app.models.analysis import AnalysisRun
from app.models.job import Job
from app.schemas.job import JobRead
from app.services import dialogue as svc
from app.services import studio

router = APIRouter(tags=["analysis"])

Stage = Literal["read", "dialogue"]
ANALYSIS_JOBS = ("analysis_read", "analysis_dialogue")


class AnalysisIn(BaseModel):
    mode: Literal["api", "manual"] = "api"
    # read via API: also queue the dialogue polish right after it (default)
    then_dialogue: bool = True
    force_all: bool = False


class PasteIn(BaseModel):
    unit_index: Optional[int] = Field(default=None, ge=0)
    raw: str = Field(min_length=1, max_length=2_000_000)


def _cancel_orphans(cid: str) -> None:
    """A queued `dialogue` job whose `read` parent failed would block the chapter forever —
    starting a new analysis supersedes it."""
    with Session(db.engine) as s:
        queued = s.exec(
            select(Job).where(Job.status == "queued", Job.type.in_(ANALYSIS_JOBS))
        ).all()
        orphans = []
        for j in queued:
            if (j.payload or {}).get("chapter_id") != cid or not j.depends_on:
                continue
            parents = [s.get(Job, d) for d in j.depends_on]
            if any(p is None or p.status in ("failed", "cancelled") for p in parents):
                orphans.append(j.id)
    for jid in orphans:
        job_service.cancel(jid)


@router.post("/chapters/{cid}/analysis/{stage}")
def start_analysis(cid: str, stage: Stage, body: AnalysisIn) -> dict[str, Any]:
    ch = stages.assert_analyzable(cid)
    _cancel_orphans(cid)
    studio.assert_chapter_idle(cid)
    if stage == "dialogue" and ch.status not in ("dialogue_draft", "dialogue_approved"):
        raise AppError(
            "READ_FIRST", "Chạy bước đọc truyện trước khi biên tập thoại", status_code=409
        )
    if body.mode == "manual":
        return {
            "mode": "manual",
            "stage": stage,
            "units": stages.prepare_manual(cid, stage, force_all=body.force_all),
        }
    jobs = []
    if stage == "read":
        if body.force_all:
            stages.reset_dialogue(cid)
        read = job_service.enqueue(
            "analysis_read", {"chapter_id": cid, "force_all": body.force_all}
        )
        jobs.append(read)
        if body.then_dialogue:
            jobs.append(
                job_service.enqueue(
                    "analysis_dialogue",
                    {"chapter_id": cid, "force_all": body.force_all},
                    depends_on=[read.id],
                )
            )
    else:
        if body.force_all:
            stages.reset_dialogue_runs(cid)
        jobs.append(
            job_service.enqueue(
                "analysis_dialogue", {"chapter_id": cid, "force_all": body.force_all}
            )
        )
    return {
        "mode": "api",
        "stage": stage,
        "jobs": [JobRead.model_validate(j).model_dump(mode="json") for j in jobs],
    }


@router.get("/chapters/{cid}/analysis/{stage}/units")
def list_units(cid: str, stage: Stage) -> list[dict[str, Any]]:
    return stages.list_units(cid, stage)


def _run_id(cid: str, stage: str, unit_index: int) -> str:
    for u in stages.list_units(cid, stage):
        if u["unit_index"] == unit_index:
            return u["id"]
    raise AppError(
        "RUN_NOT_FOUND", "Không tìm thấy phần việc — hãy bấm 'Chế độ thủ công' lại", status_code=404
    )


@router.get("/chapters/{cid}/analysis/{stage}/bundle")
def manual_bundle(cid: str, stage: Stage, unit: int = 0) -> FileResponse:
    path = stages.manual_bundle(_run_id(cid, stage, unit))
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.post("/chapters/{cid}/analysis/{stage}/paste")
def manual_paste(cid: str, stage: Stage, body: PasteIn) -> dict[str, Any]:
    studio.assert_chapter_idle(cid)

    # Attempt to extract JSON from raw
    try:
        data = extract_json(body.raw)
    except Exception as e:
        if body.unit_index is not None:
            return stages.manual_paste(_run_id(cid, stage, body.unit_index), body.raw)
        raise AppError(
            "INVALID_OUTPUT",
            "Nội dung dán vào không phải JSON hợp lệ",
            {"error": str(e)[:2000]},
            status_code=422,
        )

    json_targets: list[str] = []
    if stage == "read":
        frames = (
            data.get("frames", [])
            if isinstance(data, dict)
            else (data if isinstance(data, list) else [])
        )
        json_targets = [
            f.get("frame_id") for f in frames if isinstance(f, dict) and f.get("frame_id")
        ]
    elif stage == "dialogue":
        lines = (
            data.get("lines", [])
            if isinstance(data, dict)
            else (data if isinstance(data, list) else [])
        )
        json_targets = [
            line_item.get("line_id")
            for line_item in lines
            if isinstance(line_item, dict) and line_item.get("line_id")
        ]

    if body.unit_index is not None and not json_targets:
        return stages.manual_paste(_run_id(cid, stage, body.unit_index), body.raw)

    target_name = "frame_id" if stage == "read" else "line_id"

    with Session(db.engine) as s:
        awaiting_runs = s.exec(
            select(AnalysisRun)
            .where(
                AnalysisRun.chapter_id == cid,
                AnalysisRun.stage == stage,
                AnalysisRun.status == "awaiting_paste",
            )
            .order_by(AnalysisRun.unit_index)
        ).all()
        all_runs = s.exec(
            select(AnalysisRun)
            .where(
                AnalysisRun.chapter_id == cid,
                AnalysisRun.stage == stage,
            )
            .order_by(AnalysisRun.unit_index)
        ).all()

        active_runs = awaiting_runs if awaiting_runs else all_runs

        matched_run: Optional[AnalysisRun] = None
        set_json = set(json_targets)
        if set_json:
            for r in awaiting_runs:
                unit_targets = set((r.payload or {}).get("targets", []))
                if set_json == unit_targets:
                    matched_run = r
                    break
            if not matched_run:
                for r in all_runs:
                    unit_targets = set((r.payload or {}).get("targets", []))
                    if set_json == unit_targets:
                        matched_run = r
                        break

        if not matched_run:
            lines_desc = [
                f"Gói {r.unit_index + 1}: {', '.join(r.payload.get('targets', []))}"
                for r in active_runs
                if r.payload and r.payload.get("targets")
            ]
            err_msg = (
                f"Không tìm thấy gói nào khớp với các {target_name} trong JSON vừa dán. "
                f"Danh sách {target_name} mong đợi của từng gói còn chờ: {'; '.join(lines_desc)}"
            )
            if body.unit_index is not None:
                for r in active_runs:
                    if r.unit_index == body.unit_index:
                        r.error = err_msg[:2000]
                        s.add(r)
                        s.commit()
                        break
            raise AppError(
                "UNMATCHED_TARGETS",
                err_msg,
                {
                    "error": err_msg,
                    "stage": stage,
                    "json_targets": json_targets,
                    "expected_by_unit": {
                        str(r.unit_index + 1): r.payload.get("targets", [])
                        for r in active_runs
                        if r.payload and r.payload.get("targets")
                    },
                },
                status_code=422,
            )

        run_id = matched_run.id
        matched_idx = matched_run.unit_index

    res = stages.manual_paste(run_id, body.raw)
    res["matched_unit"] = matched_idx
    if body.unit_index is not None and body.unit_index != matched_idx:
        res["message_vi"] = f"Kết quả thuộc gói {matched_idx + 1}, đã tự chuyển"
    else:
        res["message_vi"] = f"Đã áp dụng kết quả vào gói {matched_idx + 1}"
    return res


# --- dialogue script --------------------------------------------------------
class LinePatch(BaseModel):
    text: Optional[str] = Field(default=None, max_length=2000)
    speaker_key: Optional[str] = None
    speaker_label: Optional[str] = Field(default=None, max_length=100)
    kind: Optional[TextKind] = None
    anchor_frame_id: Optional[str] = None
    reviewed: Optional[bool] = None
    speaker_suggestion: Optional[dict[str, Any]] = None


@router.get("/chapters/{cid}/dialogue")
def get_dialogue(cid: str) -> dict[str, Any]:
    return svc.get_dialogue(cid)


@router.patch("/dialogue/{lid}")
def patch_line(lid: str, body: LinePatch) -> dict[str, Any]:
    return svc.update_line(lid, body.model_dump(exclude_unset=True))


@router.post("/dialogue/{lid}/apply-speaker-suggestion")
def apply_speaker_suggestion(lid: str) -> dict[str, Any]:
    return svc.apply_speaker_suggestion(lid)


@router.post("/dialogue/{lid}/revert")
def revert_line(lid: str) -> dict[str, Any]:
    return svc.revert_line(lid)


@router.post("/chapters/{cid}/dialogue/review-all")
def review_all(cid: str) -> dict[str, Any]:
    return svc.review_all(cid)


@router.post("/chapters/{cid}/dialogue/approve")
def approve(cid: str) -> dict[str, Any]:
    return svc.approve_dialogue(cid)


@router.post("/chapters/{cid}/dialogue/apply-glossary")
def apply_glossary(cid: str) -> dict[str, Any]:
    return svc.reapply_glossary(cid)


class FramePatch(BaseModel):
    frame_type: FrameType


@router.patch("/frames/{fid}")
def patch_frame(fid: str, body: FramePatch) -> dict[str, Any]:
    return svc.set_frame_type(fid, body.frame_type)


# --- glossary ---------------------------------------------------------------
Status = Literal["suggested", "approved", "rejected"]


class TermIn(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    kind: TermKind = "other"
    variants: list[str] = []
    note: Optional[str] = Field(default=None, max_length=1000)
    status: Status = "approved"


class TermPatch(BaseModel):
    term: Optional[str] = Field(default=None, min_length=1, max_length=200)
    kind: Optional[TermKind] = None
    variants: Optional[list[str]] = None
    note: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[Status] = None


class MergeIn(BaseModel):
    into_id: str


@router.get("/projects/{pid}/glossary")
def list_glossary(pid: str) -> list[dict[str, Any]]:
    return svc.list_glossary(pid)


@router.post("/projects/{pid}/glossary", status_code=201)
def create_term(pid: str, body: TermIn) -> dict[str, Any]:
    return svc.create_term(pid, body.model_dump())


@router.patch("/glossary/{tid}")
def update_term(tid: str, body: TermPatch) -> dict[str, Any]:
    return svc.update_term(tid, body.model_dump(exclude_unset=True))


@router.delete("/glossary/{tid}")
def delete_term(tid: str) -> dict[str, Any]:
    return svc.delete_term(tid)


@router.post("/glossary/{tid}/merge")
def merge_term(tid: str, body: MergeIn) -> dict[str, Any]:
    return svc.merge_term(tid, body.into_id)


# --- address rules ------------------------------------------------------------
class RuleIn(BaseModel):
    speaker_key: str = Field(min_length=1)
    listener_key: str = Field(min_length=1)
    self_term: str = Field(min_length=1, max_length=50)
    address_term: str = Field(min_length=1, max_length=50)
    note: Optional[str] = Field(default=None, max_length=1000)
    status: Status = "approved"


class RulePatch(BaseModel):
    self_term: Optional[str] = Field(default=None, min_length=1, max_length=50)
    address_term: Optional[str] = Field(default=None, min_length=1, max_length=50)
    note: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[Status] = None


@router.get("/projects/{pid}/address-rules")
def list_rules(pid: str) -> list[dict[str, Any]]:
    return svc.list_address_rules(pid)


@router.post("/projects/{pid}/address-rules", status_code=201)
def create_rule(pid: str, body: RuleIn) -> dict[str, Any]:
    return svc.create_address_rule(pid, body.model_dump())


@router.patch("/address-rules/{rid}")
def update_rule(rid: str, body: RulePatch) -> dict[str, Any]:
    return svc.update_address_rule(rid, body.model_dump(exclude_unset=True))


@router.delete("/address-rules/{rid}")
def delete_rule(rid: str) -> dict[str, Any]:
    return svc.delete_address_rule(rid)


# --- characters -----------------------------------------------------------------
HeightClass = Literal["child", "short", "average", "tall", "giant"]
LookStatus = Literal["draft", "approved"]


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    key: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]+$")
    aliases: list[str] = []
    gender: Gender = "unknown"
    age_group: Age = "unknown"
    voice_style: Optional[str] = Field(default=None, max_length=200)
    look_lock: Optional[str] = None
    height_class: HeightClass = "average"
    ref_frame_ids: list[str] = []
    look_status: LookStatus = "draft"
    status: Literal["suggested", "approved", "rejected"] = "approved"
    role: Role = "supporting"
    role_source: Literal["ai", "user"] = "user"
    is_group: bool = False
    group_size_hint: Optional[str] = None


class CharacterPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    aliases: Optional[list[str]] = None
    gender: Optional[Gender] = None
    age_group: Optional[Age] = None
    voice_style: Optional[str] = Field(default=None, max_length=200)
    status: Optional[Literal["suggested", "approved", "rejected"]] = None
    look_lock: Optional[str] = None
    height_class: Optional[HeightClass] = None
    ref_frame_ids: Optional[list[str]] = None
    look_status: Optional[LookStatus] = None
    role: Optional[Role] = None
    role_source: Optional[Literal["ai", "user"]] = None
    is_group: Optional[bool] = None
    group_size_hint: Optional[str] = None
    profile_proposal: Optional[dict[str, Any]] = None


class ApplyProposalIn(BaseModel):
    fields: Optional[list[str]] = None


@router.get("/projects/{pid}/characters")
def list_characters(pid: str) -> list[dict[str, Any]]:
    return svc.list_characters(pid)


@router.post("/projects/{pid}/characters", status_code=201)
def create_character(pid: str, body: CharacterIn) -> dict[str, Any]:
    return svc.create_character(pid, body.model_dump())


@router.patch("/characters/{chid}")
def update_character(chid: str, body: CharacterPatch) -> dict[str, Any]:
    return svc.update_character(chid, body.model_dump(exclude_unset=True))


@router.delete("/characters/{chid}")
def delete_character(chid: str) -> dict[str, Any]:
    return svc.delete_character(chid)


@router.post("/characters/{chid}/merge")
def merge_character(chid: str, body: MergeIn) -> dict[str, Any]:
    return svc.merge_character(chid, body.into_id)


@router.post("/characters/{chid}/apply-proposal")
def apply_proposal(chid: str, body: ApplyProposalIn) -> dict[str, Any]:
    return svc.apply_proposal(chid, body.fields)
