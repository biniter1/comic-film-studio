"""Phase 1 REST API (SPEC §9): projects, chapters, import, pages, frames, assets."""

import json
import uuid
from typing import Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.errors import AppError
from app.frames.images import MAX_IMAGE_BYTES
from app.importer.url import UnsafeUrlError, validate_url
from app.jobs.runner import job_service
from app.schemas.job import JobRead
from app.services import studio
from app.storage import tmp_dir

router = APIRouter(tags=["studio"])

MAX_FILES_PER_UPLOAD = 500


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TitleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class UrlIn(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class PageOrderItem(BaseModel):
    id: str
    excluded: bool = False


class PagesIn(BaseModel):
    pages: list[PageOrderItem]


class FrameRange(BaseModel):
    y0: int
    y1: int


class FramesIn(BaseModel):
    frames: list[FrameRange]


# --- projects ---------------------------------------------------------------
@router.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    return studio.list_projects()


@router.post("/projects", status_code=201)
def create_project(body: NameIn) -> dict[str, Any]:
    return studio.create_project(body.name).model_dump(mode="json")


@router.get("/projects/{pid}")
def get_project(pid: str) -> dict[str, Any]:
    return studio.get_project(pid).model_dump(mode="json")


@router.patch("/projects/{pid}")
def rename_project(pid: str, body: NameIn) -> dict[str, Any]:
    return studio.rename_project(pid, body.name).model_dump(mode="json")


@router.delete("/projects/{pid}")
def delete_project(pid: str, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise AppError(
            "CONFIRM_REQUIRED",
            "Xóa dự án cần xác nhận (?confirm=true). File sẽ được chuyển vào thư mục trash.",
            status_code=400,
        )
    studio.delete_project(pid)
    return {"deleted": pid}


# --- chapters ---------------------------------------------------------------
@router.get("/projects/{pid}/chapters")
def list_chapters(pid: str) -> list[dict[str, Any]]:
    return studio.list_chapters(pid)


@router.post("/projects/{pid}/chapters", status_code=201)
def create_chapter(pid: str, body: TitleIn) -> dict[str, Any]:
    ch = studio.create_chapter(pid, body.title)
    return studio.chapter_detail(ch.id)


@router.get("/chapters/{cid}")
def get_chapter(cid: str) -> dict[str, Any]:
    return studio.chapter_detail(cid)


@router.patch("/chapters/{cid}")
def rename_chapter(cid: str, body: TitleIn) -> dict[str, Any]:
    studio.rename_chapter(cid, body.title)
    return studio.chapter_detail(cid)


@router.delete("/chapters/{cid}")
def delete_chapter(cid: str, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise AppError(
            "CONFIRM_REQUIRED", "Xóa chapter cần xác nhận (?confirm=true)", status_code=400
        )
    studio.delete_chapter(cid)
    return {"deleted": cid}


# --- import -----------------------------------------------------------------
@router.post("/chapters/{cid}/import/files", response_model=JobRead)
def import_files(cid: str, files: list[UploadFile] = File(...)) -> JobRead:
    studio.get_chapter(cid)
    studio.assert_chapter_idle(cid)
    if not files:
        raise AppError("VALIDATION_FAILED", "Chưa chọn file nào", status_code=422)
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise AppError(
            "VALIDATION_FAILED",
            f"Tối đa {MAX_FILES_PER_UPLOAD} file mỗi lần tải lên",
            status_code=422,
        )
    upload_id = f"upload_{uuid.uuid4().hex[:12]}"
    up = tmp_dir(settings.data_dir) / upload_id
    up.mkdir(parents=True)
    manifest = []
    for i, f in enumerate(files, 1):
        # Never use the client's filename on disk (Windows-invalid chars, traversal).
        name = (f.filename or f"file_{i}").replace("\\", "/").rsplit("/", 1)[-1][:255]
        dest = up / f"{i:04d}.bin"
        size = 0
        too_big = False
        with open(dest, "wb") as out:
            while chunk := f.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    too_big = True
                    break
                out.write(chunk)
        if too_big:
            dest.unlink(missing_ok=True)
            manifest.append({"name": name, "file": None, "error": "File quá lớn (> 30MB)"})
        else:
            manifest.append({"name": name, "file": dest.name})
    (up / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    job = job_service.enqueue("import_local", {"chapter_id": cid, "upload_id": upload_id})
    return JobRead.model_validate(job)


@router.post("/chapters/{cid}/import/url", response_model=JobRead)
def import_url(cid: str, body: UrlIn) -> JobRead:
    studio.get_chapter(cid)
    studio.assert_chapter_idle(cid)
    try:
        url = validate_url(body.url)
    except UnsafeUrlError as e:
        raise AppError("UNSAFE_URL", str(e), status_code=422) from e
    job = job_service.enqueue("import_url", {"chapter_id": cid, "url": url})
    return JobRead.model_validate(job)


@router.get("/chapters/{cid}/import/report")
def get_import_report(cid: str) -> dict[str, Any]:
    return studio.import_report(cid) or {"added": [], "rejected": [], "duplicates": []}


# --- pages ------------------------------------------------------------------
@router.get("/chapters/{cid}/pages")
def list_pages(cid: str) -> list[dict[str, Any]]:
    return studio.list_pages(cid)


@router.patch("/chapters/{cid}/pages")
def update_pages(cid: str, body: PagesIn) -> list[dict[str, Any]]:
    return studio.update_pages(cid, [p.model_dump() for p in body.pages])


# --- frames -----------------------------------------------------------------
@router.post("/chapters/{cid}/frames/auto", response_model=JobRead)
def auto_frames(cid: str) -> JobRead:
    detail = studio.chapter_detail(cid)
    studio.assert_chapter_idle(cid)
    if detail["page_count"] == 0:
        raise AppError("NO_PAGES", "Chapter chưa có trang nào để cắt khung", status_code=409)
    job = job_service.enqueue("stitch_and_cut", {"chapter_id": cid})
    return JobRead.model_validate(job)


@router.get("/chapters/{cid}/frames")
def get_frames(cid: str) -> dict[str, Any]:
    return studio.get_frames(cid)


@router.put("/chapters/{cid}/frames")
def put_frames(cid: str, body: FramesIn) -> dict[str, Any]:
    return studio.put_frames(cid, [(f.y0, f.y1) for f in body.frames])


@router.post("/chapters/{cid}/frames/approve")
def approve_frames(cid: str) -> dict[str, Any]:
    return studio.approve_frames(cid)


# --- assets -----------------------------------------------------------------
@router.get("/assets/{aid}/file")
def asset_file(aid: str) -> FileResponse:
    path = studio.asset_file(aid)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
