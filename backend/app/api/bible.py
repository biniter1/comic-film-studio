"""Phase 2b REST API (SPEC §4.6, §5.2, §9): Bible, outfits, locations, sheets."""

from typing import Any, Literal, Optional

from fastapi import APIRouter, File, Form, Response, UploadFile
from pydantic import BaseModel, Field

from app.errors import AppError
from app.frames.images import MAX_IMAGE_BYTES
from app.services import bible as svc

router = APIRouter(tags=["bible"])

TargetType = Literal["outfits", "locations"]


# --- Outfits -------------------------------------------------------------------
class OutfitIn(BaseModel):
    name_vi: str = Field(min_length=1, max_length=100)
    key: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]+$")
    outfit_lock: Optional[str] = None
    short_id: Optional[str] = Field(default=None, max_length=100)
    is_default: bool = False
    note: Optional[str] = Field(default=None, max_length=1000)


class OutfitPatch(BaseModel):
    name_vi: Optional[str] = Field(default=None, min_length=1, max_length=100)
    key: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]+$")
    outfit_lock: Optional[str] = None
    short_id: Optional[str] = Field(default=None, max_length=100)
    is_default: Optional[bool] = None
    note: Optional[str] = Field(default=None, max_length=1000)


@router.get("/characters/{chid}/outfits")
def list_outfits(chid: str) -> list[dict[str, Any]]:
    return svc.list_outfits(chid)


@router.post("/characters/{chid}/outfits", status_code=201)
def create_outfit(chid: str, body: OutfitIn) -> dict[str, Any]:
    return svc.create_outfit(chid, body.model_dump())


@router.patch("/outfits/{oid}")
def update_outfit(oid: str, body: OutfitPatch) -> dict[str, Any]:
    return svc.update_outfit(oid, body.model_dump(exclude_unset=True))


@router.delete("/outfits/{oid}")
def delete_outfit(oid: str) -> dict[str, Any]:
    return svc.delete_outfit(oid)


# --- Locations -----------------------------------------------------------------
class LocationIn(BaseModel):
    name_vi: str = Field(min_length=1, max_length=100)
    key: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]+$")
    aliases: list[str] = []
    location_lock: Optional[str] = None
    ref_frame_ids: list[str] = []


class LocationPatch(BaseModel):
    name_vi: Optional[str] = Field(default=None, min_length=1, max_length=100)
    key: Optional[str] = Field(default=None, pattern=r"^[a-z0-9_]+$")
    aliases: Optional[list[str]] = None
    location_lock: Optional[str] = None
    ref_frame_ids: Optional[list[str]] = None


@router.get("/projects/{pid}/locations")
def list_locations(pid: str) -> list[dict[str, Any]]:
    return svc.list_locations(pid)


@router.post("/projects/{pid}/locations", status_code=201)
def create_location(pid: str, body: LocationIn) -> dict[str, Any]:
    return svc.create_location(pid, body.model_dump())


@router.patch("/locations/{lid}")
def update_location(lid: str, body: LocationPatch) -> dict[str, Any]:
    return svc.update_location(lid, body.model_dump(exclude_unset=True))


@router.delete("/locations/{lid}")
def delete_location(lid: str) -> dict[str, Any]:
    return svc.delete_location(lid)


# --- Frame suggestions ---------------------------------------------------------
@router.get("/characters/{chid}/frame-suggestions")
def get_frame_suggestions(chid: str) -> list[dict[str, Any]]:
    return svc.suggest_frames(chid)


# --- Story Bible ---------------------------------------------------------------
@router.get("/projects/{pid}/bible")
def get_project_bible(pid: str) -> dict[str, Any]:
    return svc.get_bible(pid)


# --- Sheet bundle & upload (Shared: outfits | locations) -----------------------
@router.get("/{target}/{id}/sheet-bundle")
def download_sheet_bundle(target: str, id: str) -> Response:
    if target not in ("outfits", "locations"):
        raise AppError("INVALID_TARGET", f"Mục tiêu '{target}' không hợp lệ", status_code=400)
    zip_bytes, filename = svc.get_sheet_bundle(target, id)  # type: ignore[arg-type]
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{target}/{id}/sheet")
def upload_sheet(target: str, id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    if target not in ("outfits", "locations"):
        raise AppError("INVALID_TARGET", f"Mục tiêu '{target}' không hợp lệ", status_code=400)
    content = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        max_mb = MAX_IMAGE_BYTES // (1024 * 1024)
        raise AppError(
            "FILE_TOO_LARGE",
            f"Ảnh quá lớn (tối đa {max_mb} MB)",
            status_code=413,
        )
    return svc.upload_sheet(target, id, content)  # type: ignore[arg-type]


@router.post("/{target}/{id}/sheet/approve")
def approve_sheet(target: str, id: str) -> dict[str, Any]:
    if target not in ("outfits", "locations"):
        raise AppError("INVALID_TARGET", f"Mục tiêu '{target}' không hợp lệ", status_code=400)
    return svc.approve_sheet(target, id)  # type: ignore[arg-type]


@router.post("/{target}/{id}/sheet/reject")
def reject_sheet(target: str, id: str) -> dict[str, Any]:
    if target not in ("outfits", "locations"):
        raise AppError("INVALID_TARGET", f"Mục tiêu '{target}' không hợp lệ", status_code=400)
    return svc.reject_sheet(target, id)  # type: ignore[arg-type]


# --- Character References & Look Profile ---------------------------------------
class CropIn(BaseModel):
    frame_id: str
    x0: int
    y0: int
    x1: int
    y1: int
    outfit_id: Optional[str] = None
    note: Optional[str] = None


class RefPatch(BaseModel):
    outfit_id: Optional[str] = None
    order: Optional[int] = None
    note: Optional[str] = None


@router.post("/characters/{chid}/refs/crop", status_code=201)
def crop_character_ref(chid: str, body: CropIn) -> dict[str, Any]:
    return svc.create_character_ref_from_crop(
        chid, body.frame_id, body.x0, body.y0, body.x1, body.y1, body.outfit_id, body.note
    )


@router.post("/characters/{chid}/refs/upload", status_code=201)
def upload_character_ref(
    chid: str,
    file: UploadFile = File(...),
    outfit_id: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
) -> dict[str, Any]:
    content = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        max_mb = MAX_IMAGE_BYTES // (1024 * 1024)
        raise AppError("FILE_TOO_LARGE", f"Ảnh quá lớn (tối đa {max_mb} MB)", status_code=413)
    return svc.create_character_ref_from_upload(chid, content, outfit_id, note)


@router.get("/characters/{chid}/refs")
def list_character_refs(chid: str) -> list[dict[str, Any]]:
    return svc.list_character_refs(chid)


@router.delete("/refs/{rid}")
def delete_character_ref(rid: str) -> dict[str, Any]:
    return svc.delete_character_ref(rid)


@router.patch("/refs/{rid}")
def update_character_ref(rid: str, body: RefPatch) -> dict[str, Any]:
    return svc.update_character_ref(rid, body.model_dump(exclude_unset=True))


@router.post("/characters/{chid}/look-profile")
def request_look_profile(chid: str) -> dict[str, Any]:
    return svc.enqueue_look_profile(chid)
