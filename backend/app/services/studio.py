"""Domain logic for Phase 1: projects, chapters, source pages, frames (SPEC §3, §6).

All functions are synchronous (called from `def` endpoints or `def` job handlers, i.e. worker
threads) and open their own DB sessions. Files live under the project directory; the DB stores
paths relative to it.
"""

import json
import re
import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app import db
from app.config import settings
from app.errors import AppError
from app.frames import strip as stripmod
from app.frames.images import check_image, make_preview
from app.jobs.event_bus import event_bus
from app.models.analysis import AnalysisRun, DialogueLine
from app.models.job import Job
from app.models.project import Asset, Chapter, Frame, Project, SourcePage, new_id
from app.storage import asset_abs_path, chapter_dir, project_dir, to_relative

Progress = Callable[[float, str | None], None]
CHAPTER_JOB_TYPES = (
    "import_local",
    "import_url",
    "stitch_and_cut",
    "analysis_read",
    "analysis_dialogue",
    "analysis_plan",
    "analysis_shots",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session() -> Session:
    return Session(db.engine)


def natural_key(name: str) -> list[Any]:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _emit_chapter(ch: Chapter) -> None:
    event_bus.publish_threadsafe(
        "chapter.updated", {"id": ch.id, "project_id": ch.project_id, "status": ch.status}
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
def create_project(name: str) -> Project:
    name = name.strip()
    if not name:
        raise AppError("VALIDATION_FAILED", "Tên dự án không được để trống", status_code=422)
    p = Project(name=name)
    with _session() as s:
        s.add(p)
        s.commit()
        s.refresh(p)
    d = project_dir(p.id)
    (d / "chapters").mkdir(parents=True, exist_ok=True)
    (d / "refs").mkdir(parents=True, exist_ok=True)
    return p


def get_project(pid: str) -> Project:
    with _session() as s:
        p = s.get(Project, pid)
        if not p:
            raise AppError("PROJECT_NOT_FOUND", "Không tìm thấy dự án", status_code=404)
        return p


def list_projects() -> list[dict[str, Any]]:
    with _session() as s:
        projects = s.exec(select(Project).order_by(Project.updated_at.desc())).all()
        out = []
        for p in projects:
            chapters = s.exec(select(Chapter).where(Chapter.project_id == p.id)).all()
            out.append(
                {
                    **p.model_dump(mode="json"),
                    "chapter_count": len(chapters),
                    "storage_bytes": _dir_size(project_dir(p.id)),
                }
            )
        return out


def rename_project(pid: str, name: str) -> Project:
    name = name.strip()
    if not name:
        raise AppError("VALIDATION_FAILED", "Tên dự án không được để trống", status_code=422)
    with _session() as s:
        p = s.get(Project, pid)
        if not p:
            raise AppError("PROJECT_NOT_FOUND", "Không tìm thấy dự án", status_code=404)
        p.name = name
        p.updated_at = _now()
        s.add(p)
        s.commit()
        s.refresh(p)
        return p


def delete_project(pid: str) -> None:
    """Move files to data_dir/trash/ (recoverable) and remove DB rows."""
    with _session() as s:
        p = s.get(Project, pid)
        if not p:
            raise AppError("PROJECT_NOT_FOUND", "Không tìm thấy dự án", status_code=404)
        for ch in s.exec(select(Chapter).where(Chapter.project_id == pid)).all():
            _assert_chapter_idle(s, ch.id)
            _delete_chapter_rows(s, ch.id)
        for a in s.exec(select(Asset).where(Asset.project_id == pid)).all():
            s.delete(a)
        s.delete(p)
        s.commit()
    _move_to_trash(project_dir(pid), f"project_{pid}")


def _move_to_trash(path: Path, label: str) -> None:
    if not path.exists():
        return
    trash = settings.data_dir / "trash"
    trash.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(trash / f"{label}_{_now().strftime('%Y%m%d-%H%M%S')}"))


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------
def create_chapter(pid: str, title: str) -> Chapter:
    title = title.strip()
    if not title:
        raise AppError("VALIDATION_FAILED", "Tên chapter không được để trống", status_code=422)
    get_project(pid)
    ch = Chapter(project_id=pid, title=title)
    with _session() as s:
        s.add(ch)
        p = s.get(Project, pid)
        if p:
            p.updated_at = _now()
            s.add(p)
        s.commit()
        s.refresh(ch)
    d = chapter_dir(pid, ch.id)
    for sub in ("pages/preview", "frames"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return ch


def get_chapter(cid: str) -> Chapter:
    with _session() as s:
        ch = s.get(Chapter, cid)
        if not ch:
            raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
        return ch


def list_chapters(pid: str) -> list[dict[str, Any]]:
    get_project(pid)
    with _session() as s:
        chs = s.exec(
            select(Chapter).where(Chapter.project_id == pid).order_by(Chapter.created_at)
        ).all()
        return [chapter_summary(s, ch) for ch in chs]


def chapter_summary(s: Session, ch: Chapter) -> dict[str, Any]:
    pages = s.exec(select(SourcePage).where(SourcePage.chapter_id == ch.id)).all()
    frames = s.exec(select(Frame).where(Frame.chapter_id == ch.id)).all()
    return {
        **ch.model_dump(mode="json"),
        "page_count": sum(p.status == "ok" for p in pages),
        "excluded_page_count": sum(p.status == "excluded" for p in pages),
        "frame_count": len(frames),
        "busy_job_id": active_chapter_job(s, ch.id),
    }


def chapter_detail(cid: str) -> dict[str, Any]:
    with _session() as s:
        ch = s.get(Chapter, cid)
        if not ch:
            raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
        return chapter_summary(s, ch)


def rename_chapter(cid: str, title: str) -> Chapter:
    title = title.strip()
    if not title:
        raise AppError("VALIDATION_FAILED", "Tên chapter không được để trống", status_code=422)
    with _session() as s:
        ch = s.get(Chapter, cid)
        if not ch:
            raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
        ch.title = title
        ch.updated_at = _now()
        s.add(ch)
        s.commit()
        s.refresh(ch)
        return ch


def delete_chapter(cid: str) -> None:
    with _session() as s:
        ch = s.get(Chapter, cid)
        if not ch:
            raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
        _assert_chapter_idle(s, cid)
        pid = ch.project_id
        _delete_chapter_rows(s, cid)
        for a in s.exec(select(Asset).where(Asset.chapter_id == cid)).all():
            s.delete(a)
        s.delete(ch)
        s.commit()
    _move_to_trash(chapter_dir(pid, cid), f"chapter_{cid}")


def drop_analysis(s: Session, cid: str) -> int:
    """Frames changed → dialogue/analysis built on them is stale (and FK-bound). Remove it."""
    from app.models.shots import Scene, Shot

    for sh in s.exec(select(Shot).where(Shot.chapter_id == cid)).all():
        s.delete(sh)
    s.flush()
    for sc in s.exec(select(Scene).where(Scene.chapter_id == cid)).all():
        s.delete(sc)
    s.flush()
    lines = s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)).all()
    for d in lines:
        s.delete(d)
    for r in s.exec(select(AnalysisRun).where(AnalysisRun.chapter_id == cid)).all():
        s.delete(r)
    s.flush()
    return len(lines)


def _delete_chapter_rows(s: Session, cid: str) -> None:
    drop_analysis(s, cid)
    for f in s.exec(select(Frame).where(Frame.chapter_id == cid)).all():
        s.delete(f)
    for p in s.exec(select(SourcePage).where(SourcePage.chapter_id == cid)).all():
        s.delete(p)
    s.flush()
    for a in s.exec(select(Asset).where(Asset.chapter_id == cid)).all():
        s.delete(a)
    s.flush()


def active_chapter_job(s: Session, cid: str) -> str | None:
    jobs = s.exec(
        select(Job).where(Job.status.in_(["queued", "running"]), Job.type.in_(CHAPTER_JOB_TYPES))
    ).all()
    for j in jobs:
        if (j.payload or {}).get("chapter_id") == cid:
            return j.id
    return None


def _assert_chapter_idle(s: Session, cid: str) -> None:
    jid = active_chapter_job(s, cid)
    if jid:
        raise AppError(
            "CHAPTER_BUSY",
            f"Chapter đang có việc chạy nền ({jid}). Chờ xong hoặc hủy job đó trước.",
            details={"job_id": jid},
            status_code=409,
        )


def assert_chapter_idle(cid: str) -> None:
    with _session() as s:
        _assert_chapter_idle(s, cid)


# ---------------------------------------------------------------------------
# Source pages
# ---------------------------------------------------------------------------
def ingest_images(
    cid: str,
    items: list[tuple[str, Path]],
    progress: Progress | None = None,
    pre_rejected: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate and store images as pages (appended, natural-sorted by original name).

    Idempotent: an image whose sha256 already exists in the chapter is skipped, so re-running
    an interrupted import does not create duplicates.
    """
    ch = get_chapter(cid)
    cdir = chapter_dir(ch.project_id, cid)
    (cdir / "pages" / "preview").mkdir(parents=True, exist_ok=True)
    proot = project_dir(ch.project_id)
    report: dict[str, Any] = {"added": [], "rejected": list(pre_rejected or []), "duplicates": []}

    items = sorted(items, key=lambda it: natural_key(it[0]))
    with _session() as s:
        existing = s.exec(select(SourcePage).where(SourcePage.chapter_id == cid)).all()
        known_sha = {p.sha256 for p in existing}
        next_idx = max((p.idx for p in existing), default=0) + 1

    total = max(1, len(items))
    for n, (name, path) in enumerate(items, 1):
        chk = check_image(path)
        if not chk.ok:
            report["rejected"].append({"name": name, "reason": chk.reason})
        elif chk.sha256 in known_sha:
            report["duplicates"].append({"name": name, "reason": "Trùng với một trang đã có"})
        else:
            idx = next_idx
            next_idx += 1
            known_sha.add(chk.sha256)
            dest = cdir / "pages" / f"{idx:03d}{chk.ext}"
            shutil.copyfile(path, dest)
            prev = cdir / "pages" / "preview" / f"{idx:03d}.jpg"
            pw, ph = make_preview(dest, prev)
            with _session() as s:
                a = Asset(
                    project_id=ch.project_id,
                    chapter_id=cid,
                    kind="page",
                    path=to_relative(proot, dest),
                    sha256=chk.sha256,
                    media={"width": chk.width, "height": chk.height, "format": chk.fmt},
                    approval="approved",
                )
                ap = Asset(
                    project_id=ch.project_id,
                    chapter_id=cid,
                    kind="page_preview",
                    path=to_relative(proot, prev),
                    parent_ids=[a.id],
                    media={"width": pw, "height": ph},
                    approval="approved",
                )
                s.add(a)
                s.add(ap)
                s.flush()
                s.add(
                    SourcePage(
                        chapter_id=cid,
                        idx=idx,
                        asset_id=a.id,
                        preview_asset_id=ap.id,
                        original_name=name[:255],
                        sha256=chk.sha256,
                        width=chk.width,
                        height=chk.height,
                    )
                )
                s.commit()
            report["added"].append({"name": name, "idx": idx})
        if progress:
            progress(n / total, f"Đã xử lý {n}/{len(items)} ảnh")

    with _session() as s:
        c = s.get(Chapter, cid)
        if c:
            if report["added"]:
                _invalidate_frames(s, c)
                c.status = "imported"
            c.updated_at = _now()
            s.add(c)
            s.commit()
            s.refresh(c)
            _emit_chapter(c)
    (cdir / "import_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def import_report(cid: str) -> dict[str, Any] | None:
    ch = get_chapter(cid)
    f = chapter_dir(ch.project_id, cid) / "import_report.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def list_pages(cid: str) -> list[dict[str, Any]]:
    get_chapter(cid)
    with _session() as s:
        pages = s.exec(
            select(SourcePage).where(SourcePage.chapter_id == cid).order_by(SourcePage.idx)
        ).all()
        return [
            {
                **p.model_dump(mode="json"),
                "url": f"/api/assets/{p.asset_id}/file",
                "preview_url": f"/api/assets/{p.preview_asset_id}/file"
                if p.preview_asset_id
                else None,
            }
            for p in pages
        ]


def update_pages(cid: str, order: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`order` lists every page id in the desired order, each with optional `excluded`."""
    with _session() as s:
        ch = s.get(Chapter, cid)
        if not ch:
            raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
        _assert_chapter_idle(s, cid)
        pages = {p.id: p for p in s.exec(select(SourcePage).where(SourcePage.chapter_id == cid))}
        ids = [str(o.get("id")) for o in order]
        if sorted(ids) != sorted(pages):
            raise AppError(
                "VALIDATION_FAILED",
                "Danh sách trang phải gồm đủ và đúng các trang của chapter",
                status_code=422,
            )
        changed = False
        for i, o in enumerate(order, 1):
            p = pages[str(o["id"])]
            status = "excluded" if o.get("excluded") else "ok"
            if p.idx != i or p.status != status:
                changed = True
            p.idx = i
            p.status = status
            s.add(p)
        if changed:
            _invalidate_frames(s, ch)
            ch.status = "imported"
            ch.updated_at = _now()
            s.add(ch)
        s.commit()
        if changed:
            s.refresh(ch)
            _emit_chapter(ch)
    return list_pages(cid)


def _invalidate_frames(s: Session, ch: Chapter) -> None:
    """Pages changed → existing frames no longer match the strip. Rows go, files/assets stay."""
    drop_analysis(s, ch.id)
    for f in s.exec(select(Frame).where(Frame.chapter_id == ch.id)).all():
        s.delete(f)
    ch.strip_width = None


# ---------------------------------------------------------------------------
# Strip & frames
# ---------------------------------------------------------------------------
def build_chapter_strip(cid: str) -> stripmod.Strip:
    ch = get_chapter(cid)
    with _session() as s:
        pages = s.exec(
            select(SourcePage)
            .where(SourcePage.chapter_id == cid, SourcePage.status == "ok")
            .order_by(SourcePage.idx)
        ).all()
        rows = []
        for p in pages:
            a = s.get(Asset, p.asset_id)
            if a:
                rows.append((p.id, asset_abs_path(ch.project_id, a.path), p.width, p.height))
    return stripmod.build_strip(rows)


def auto_frames(cid: str, progress: Progress | None = None) -> int:
    ch = get_chapter(cid)
    strip = build_chapter_strip(cid)
    if not strip.pages:
        raise AppError("NO_PAGES", "Chapter chưa có trang nào để cắt khung", status_code=409)
    if progress:
        progress(0.05, "Đang phân tích khoảng trống giữa các khung")
    ranges = stripmod.detect_frames(strip)
    with _session() as s:
        c = s.get(Chapter, cid)
        assert c
        drop_analysis(s, cid)
        for f in s.exec(select(Frame).where(Frame.chapter_id == cid)).all():
            s.delete(f)
        c.strip_width = strip.width
        s.add(c)
        s.commit()
    total = max(1, len(ranges))
    for i, (y0, y1) in enumerate(ranges, 1):
        _create_frame(ch, strip, i, y0, y1, "auto")
        if progress:
            progress(0.1 + 0.9 * i / total, f"Đã cắt {i}/{len(ranges)} khung")
    with _session() as s:
        c = s.get(Chapter, cid)
        assert c
        c.status = "frames_draft"
        c.updated_at = _now()
        s.add(c)
        s.commit()
        s.refresh(c)
        _emit_chapter(c)
    return len(ranges)


def _create_frame(ch: Chapter, strip: stripmod.Strip, idx: int, y0: int, y1: int, origin: str):
    proot = project_dir(ch.project_id)
    asset_id = new_id("A")
    dest = chapter_dir(ch.project_id, ch.id) / "frames" / f"{asset_id}.png"
    stripmod.crop_frame(strip, y0, y1).save(dest)
    with _session() as s:
        s.add(
            Asset(
                id=asset_id,
                project_id=ch.project_id,
                chapter_id=ch.id,
                kind="frame",
                path=to_relative(proot, dest),
                media={"width": strip.width, "height": y1 - y0},
            )
        )
        s.flush()
        s.add(
            Frame(
                chapter_id=ch.id,
                idx=idx,
                asset_id=asset_id,
                x0=0,
                y0=y0,
                x1=strip.width,
                y1=y1,
                origin=origin,
            )
        )
        s.commit()


def get_frames(cid: str) -> dict[str, Any]:
    ch = get_chapter(cid)
    strip = build_chapter_strip(cid)
    with _session() as s:
        previews = {
            p.id: p.preview_asset_id
            for p in s.exec(select(SourcePage).where(SourcePage.chapter_id == cid))
        }
        frames = s.exec(select(Frame).where(Frame.chapter_id == cid).order_by(Frame.idx)).all()
        busy = active_chapter_job(s, cid)
    return {
        "chapter_id": cid,
        "status": ch.status,
        "busy_job_id": busy,
        "strip": {
            "width": strip.width,
            "height": strip.height,
            "pages": [
                {
                    "page_id": p.page_id,
                    "y0": p.y0,
                    "y1": p.y1,
                    "preview_url": f"/api/assets/{previews.get(p.page_id)}/file",
                }
                for p in strip.pages
            ],
        },
        "frames": [
            {
                "id": f.id,
                "idx": f.idx,
                "y0": f.y0,
                "y1": f.y1,
                "origin": f.origin,
                "asset_id": f.asset_id,
                "url": f"/api/assets/{f.asset_id}/file",
            }
            for f in frames
        ],
    }


def put_frames(cid: str, ranges: list[tuple[int, int]]) -> dict[str, Any]:
    """Replace the frame list. Unchanged ranges keep their crop; new ranges are cropped from
    the original pages. Old assets are kept (versions), only Frame rows change."""
    ch = get_chapter(cid)
    assert_chapter_idle(cid)
    strip = build_chapter_strip(cid)
    if not strip.pages:
        raise AppError("NO_PAGES", "Chapter chưa có trang nào", status_code=409)
    err = stripmod.validate_ranges(ranges, strip.height)
    if err:
        raise AppError("VALIDATION_FAILED", err, status_code=422)
    with _session() as s:
        existing = {(f.y0, f.y1): f for f in s.exec(select(Frame).where(Frame.chapter_id == cid))}
        keep = set(ranges)
        changed = set(existing) != keep
        removed = [f for key, f in existing.items() if key not in keep]
        if removed:
            gone = {f.id for f in removed}
            for d in s.exec(select(DialogueLine).where(DialogueLine.chapter_id == cid)):
                if d.source_frame_id in gone:
                    s.delete(d)
                elif d.anchor_frame_id in gone:
                    d.anchor_frame_id = None
                    d.anchor_locked = False
                    s.add(d)
            for r in s.exec(
                select(AnalysisRun).where(
                    AnalysisRun.chapter_id == cid, AnalysisRun.stage == "read"
                )
            ):
                cur_targets = (r.payload or {}).get("targets", [])
                new_targets = [fid for fid in cur_targets if fid not in gone]
                if len(new_targets) != len(cur_targets):
                    r.payload = {**(r.payload or {}), "targets": new_targets}
                    s.add(r)
            s.flush()
            from app.models.shots import Scene, Shot

            for row in [
                *s.exec(select(Scene).where(Scene.chapter_id == cid)),
                *s.exec(select(Shot).where(Shot.chapter_id == cid)),
            ]:
                kept = [fid for fid in row.frame_ids if fid not in gone]
                if len(kept) != len(row.frame_ids):
                    row.frame_ids = kept
                    s.add(row)
            s.flush()
        for f in removed:
            s.delete(f)
        for i, key in enumerate(ranges, 1):
            if key in existing:
                existing[key].idx = i
                s.add(existing[key])
        c = s.get(Chapter, cid)
        assert c
        c.strip_width = strip.width
        s.add(c)
        s.commit()
    for i, (y0, y1) in enumerate(ranges, 1):
        if (y0, y1) not in existing:
            _create_frame(ch, strip, i, y0, y1, "manual")
    with _session() as s:
        c = s.get(Chapter, cid)
        from app.analysis import stages

        unread_units = stages.read_units(cid)
        has_unread = len(unread_units) > 0
        has_script = c.status in (
            "dialogue_draft",
            "dialogue_approved",
            "shots_draft",
            "plan_approved",
        )
        if has_script:
            stages.recompute_anchors(s, cid)

        if has_unread:
            # Còn khung chưa đọc → không để chapter ở dialogue_draft như thể đã xong
            analyzable = (
                "frames_approved",
                "dialogue_draft",
                "dialogue_approved",
                "shots_draft",
                "plan_approved",
            )
            c.status = (
                "frames_approved" if (has_script or c.status in analyzable) else "frames_draft"
            )
        elif has_script:
            c.status = "dialogue_draft"
        elif changed or c.status not in (
            "frames_approved",
            "dialogue_draft",
            "dialogue_approved",
            "shots_draft",
            "plan_approved",
        ):
            c.status = "frames_draft"
        c.updated_at = _now()
        s.add(c)
        s.commit()
        s.refresh(c)
        _emit_chapter(c)
    return get_frames(cid)


def approve_frames(cid: str) -> dict[str, Any]:
    with _session() as s:
        c = s.get(Chapter, cid)
        if not c:
            raise AppError("CHAPTER_NOT_FOUND", "Không tìm thấy chapter", status_code=404)
        _assert_chapter_idle(s, cid)
        n = len(s.exec(select(Frame).where(Frame.chapter_id == cid)).all())
        if n == 0:
            raise AppError("NO_FRAMES", "Chưa có khung nào để duyệt", status_code=409)
        if c.status not in (
            "analyzing",
            "dialogue_draft",
            "dialogue_approved",
            "shots_draft",
            "plan_approved",
        ):
            c.status = "frames_approved"  # later stages keep their status (frames unchanged)
        c.updated_at = _now()
        s.add(c)
        s.commit()
        s.refresh(c)
        _emit_chapter(c)
        return chapter_summary(s, c)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
def asset_file(aid: str) -> Path:
    with _session() as s:
        a = s.get(Asset, aid)
        if not a:
            raise AppError("ASSET_NOT_FOUND", "Không tìm thấy tài nguyên", status_code=404)
        path = asset_abs_path(a.project_id, a.path)
        if not path.is_file():
            if not a.missing:
                a.missing = True
                s.add(a)
                s.commit()
            raise AppError("ASSET_MISSING", "File của tài nguyên đã bị xóa/mất", status_code=404)
        return path
