"""Phase 2a analysis jobs (SPEC §4.1, §4.5). `def` handlers → run in a worker thread."""

from sqlmodel import Session, select

from app import db
from app.analysis import stages
from app.analysis.engine import call_structured
from app.errors import AppError
from app.jobs.registry import JobContext, JobError, job_handler
from app.models.analysis import AnalysisRun, DialogueLine
from app.models.project import Chapter
from app.providers import registry
from app.providers.base import ProviderError


def _provider():
    try:
        return registry.get_provider()
    except ProviderError as e:
        raise JobError(e.category, e.message_vi, e.user_action_required) from e


def _work_dir(cid: str):
    with Session(db.engine) as s:
        ch = s.get(Chapter, cid)
        if not ch:
            raise JobError("permanent", "Chapter đã bị xóa")
        return stages.work_dir(ch)


def _run_stage(ctx: JobContext, stage: str) -> None:
    cid = ctx.payload["chapter_id"]
    units_fn, build, validator, schema, apply_fn, finalize = stages.STAGES[stage]
    provider = _provider()
    wd = _work_dir(cid)
    units = units_fn(cid)
    label = "khung" if stage == "read" else "câu"
    ctx.log(f"{stage}: {len(units)} phần việc, provider={provider.name}")
    if not units:
        finalize(cid)
        return
    for i in range(len(units)):
        if ctx.is_cancelled():
            return
        ctx.report_progress(i / len(units), f"Phần {i + 1}/{len(units)} ({len(units[i])} {label})")
        targets = units[i]

        with Session(db.engine) as s:
            existing_run = s.exec(
                select(AnalysisRun).where(
                    AnalysisRun.chapter_id == cid,
                    AnalysisRun.stage == stage,
                    AnalysisRun.unit_index == i,
                )
            ).first()

            if (
                existing_run
                and existing_run.status == "succeeded"
                and (existing_run.payload or {}).get("targets") == targets
            ):
                if stage == "read" and existing_run.payload.get("output"):
                    existing_lines = s.exec(
                        select(DialogueLine).where(
                            DialogueLine.chapter_id == cid,
                            DialogueLine.source_frame_id.in_(targets),
                        )
                    ).first()
                    expected_texts = any(
                        len(f.get("texts", [])) > 0
                        for f in existing_run.payload["output"].get("frames", [])
                    )
                    if expected_texts and not existing_lines:
                        out = schema.model_validate(existing_run.payload["output"])
                        apply_fn(
                            cid,
                            i,
                            out,
                            mode=existing_run.mode,
                            attempts=existing_run.attempts,
                            ih=existing_run.input_hash,
                        )
                ctx.log(f"phần {i + 1}: đã có kết quả, bỏ qua")
                continue

        req, built_targets = build(cid, i)
        try:
            out, attempts, ih = call_structured(
                provider,
                req,
                schema,
                prompt_version=stages.PROMPT_VERSION,
                work_dir=wd,
                extra_validate=validator(built_targets),
            )
        except ProviderError as e:
            raise JobError(e.category, e.message_vi, e.user_action_required) from e
        apply_fn(cid, i, out, mode="api", attempts=attempts, ih=ih)
        ctx.log(
            f"  phần {i + 1}: ok sau {attempts} lần gọi"
            if attempts
            else f"  phần {i + 1}: dùng cache"
        )
    finalize(cid)
    ctx.report_progress(1.0, "Xong")


@job_handler("analysis_read")
def handle_read(ctx: JobContext) -> None:
    cid = ctx.payload["chapter_id"]
    try:
        stages.assert_analyzable(cid)
        if ctx.payload.get("force_all"):
            n = stages.reset_dialogue(cid)
            if n:
                ctx.log(f"Đã sao lưu và xóa {n} câu thoại cũ (analysis/history)")
    except AppError as e:
        raise JobError("permanent", e.message_vi) from e
    _run_stage(ctx, "read")


@job_handler("analysis_dialogue")
def handle_dialogue(ctx: JobContext) -> None:
    cid = ctx.payload["chapter_id"]
    try:
        stages.assert_analyzable(cid)
        if ctx.payload.get("force_all"):
            stages.reset_dialogue_runs(cid)
    except AppError as e:
        raise JobError("permanent", e.message_vi) from e
    _run_stage(ctx, "dialogue")
