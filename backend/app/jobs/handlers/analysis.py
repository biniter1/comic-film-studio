"""Phase 2a analysis jobs (SPEC §4.1, §4.5). `def` handlers → run in a worker thread."""

from sqlmodel import Session, select

from app import db
from app.analysis import stages
from app.analysis.engine import call_structured, load_prompt
from app.analysis.schemas import LookProfileOut
from app.config import settings
from app.errors import AppError
from app.jobs.registry import JobContext, JobError, job_handler
from app.models.analysis import AnalysisRun, Character, CharacterRef, DialogueLine
from app.models.project import Asset, Chapter
from app.providers import registry
from app.providers.base import ImagePart, ProviderError, ProviderRequest
from app.storage import asset_abs_path, project_dir


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

    with Session(db.engine) as s:
        existing_succeeded = list(
            s.exec(
                select(AnalysisRun).where(
                    AnalysisRun.chapter_id == cid,
                    AnalysisRun.stage == stage,
                    AnalysisRun.status == "succeeded",
                )
            ).all()
        )
        for r in sorted(existing_succeeded, key=lambda x: x.unit_index):
            ctx.log(f"phần {r.unit_index + 1}: đã có kết quả, bỏ qua")
            targets = (r.payload or {}).get("targets", [])
            output = (r.payload or {}).get("output")
            if stage == "read" and output and targets:
                existing_lines = s.exec(
                    select(DialogueLine).where(
                        DialogueLine.chapter_id == cid,
                        DialogueLine.source_frame_id.in_(targets),
                    )
                ).first()
                expected_texts = any(len(f.get("texts", [])) > 0 for f in output.get("frames", []))
                if expected_texts and not existing_lines:
                    out = schema.model_validate(output)
                    apply_fn(
                        cid,
                        r.unit_index,
                        out,
                        mode=r.mode,
                        attempts=r.attempts,
                        ih=r.input_hash,
                        targets=targets,
                    )

    if not units:
        finalize(cid)
        return
    for i in range(len(units)):
        if ctx.is_cancelled():
            return
        ctx.report_progress(i / len(units), f"Phần {i + 1}/{len(units)} ({len(units[i])} {label})")
        targets = units[i]

        with Session(db.engine) as s:
            existing_runs = s.exec(
                select(AnalysisRun).where(
                    AnalysisRun.chapter_id == cid,
                    AnalysisRun.stage == stage,
                )
            ).all()
            matching_run = next(
                (
                    r
                    for r in existing_runs
                    if (r.payload or {}).get("targets") == targets and r.status == "succeeded"
                ),
                None,
            )

            if matching_run:
                if stage == "read" and matching_run.payload.get("output"):
                    existing_lines = s.exec(
                        select(DialogueLine).where(
                            DialogueLine.chapter_id == cid,
                            DialogueLine.source_frame_id.in_(targets),
                        )
                    ).first()
                    expected_texts = any(
                        len(f.get("texts", [])) > 0
                        for f in matching_run.payload["output"].get("frames", [])
                    )
                    if expected_texts and not existing_lines:
                        out = schema.model_validate(matching_run.payload["output"])
                        apply_fn(
                            cid,
                            matching_run.unit_index,
                            out,
                            mode=matching_run.mode,
                            attempts=matching_run.attempts,
                            ih=matching_run.input_hash,
                            targets=targets,
                        )
                ctx.log(f"phần {i + 1}: đã có kết quả, bỏ qua")
                continue

        req, built_targets = build(cid, i, targets=targets)
        try:
            out, attempts, ih = call_structured(
                provider,
                req,
                schema,
                prompt_version=stages.prompt_version_for(stage),
                work_dir=wd,
                extra_validate=validator(built_targets),
            )
        except ProviderError as e:
            raise JobError(e.category, e.message_vi, e.user_action_required) from e
        apply_fn(cid, i, out, mode="api", attempts=attempts, ih=ih, targets=built_targets)
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


@job_handler("character_profile")
def handle_character_profile(ctx: JobContext) -> None:
    chid = ctx.payload["character_id"]
    provider = _provider()

    with Session(db.engine) as s:
        char = s.get(Character, chid)
        if not char:
            raise JobError("permanent", "Không tìm thấy nhân vật")
        pid = char.project_id
        refs = s.exec(
            select(CharacterRef)
            .where(CharacterRef.character_id == chid)
            .order_by(CharacterRef.order, CharacterRef.created_at)
        ).all()
        if not refs:
            raise JobError("permanent", "Nhân vật không có ảnh tham chiếu nào")

        selected_refs = refs[:4]
        images: list[ImagePart] = []
        for idx, r in enumerate(selected_refs, 1):
            asset = s.get(Asset, r.asset_id)
            if not asset:
                continue
            abs_p = asset_abs_path(pid, asset.path)
            if abs_p.is_file():
                images.append(ImagePart(label=f"REF {idx} (ref_id: {r.id})", path=abs_p))

        if not images:
            raise JobError("permanent", "Không tìm thấy file ảnh tham chiếu nào trên đĩa")

    ctx.report_progress(0.2, "Đang phân tích hồ sơ ngoại hình từ ảnh tham chiếu...")
    user_text = (
        f"Character Name: {char.name}\n"
        f"Key: {char.key}\n"
        f"Gender: {char.gender}\n"
        f"Age Group: {char.age_group}\n"
        f"Role: {char.role}\n"
    )
    if char.voice_style:
        user_text += f"Voice Style / Personality: {char.voice_style}\n"

    wd = project_dir(pid) / "refs" / char.key
    wd.mkdir(parents=True, exist_ok=True)
    system_prompt = load_prompt("look_profile", "v1")

    req = ProviderRequest(
        stage="character_profile",
        model=settings.analysis_model_vision,
        system=system_prompt,
        user_text=user_text,
        images=images,
    )

    try:
        out, attempts, ih = call_structured(
            provider,
            req,
            LookProfileOut,
            prompt_version="v1",
            work_dir=wd,
        )
    except ProviderError as e:
        raise JobError(e.category, e.message_vi, e.user_action_required) from e

    with Session(db.engine) as s:
        char = s.get(Character, chid)
        if char:
            char.profile_proposal = out.model_dump(mode="json")
            s.add(char)
            s.commit()

    ctx.report_progress(1.0, "Đã tạo bản đề xuất hồ sơ ngoại hình")
