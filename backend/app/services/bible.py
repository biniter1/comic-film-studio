"""Phase 2b Story Bible service (SPEC §4.6, §5.2, §10).

Manages Characters (look_lock, height_class, ref_frame_ids, look_status),
CharacterOutfits, Locations, and consistency Sheets (Nano Banana handoff bundle & uploads).
"""

import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from PIL import Image
from sqlmodel import Session, select

from app import db
from app.errors import AppError
from app.frames.images import _jpeg_bytes, check_image, sha256_file
from app.jobs.runner import job_service
from app.models.analysis import Character, CharacterOutfit, CharacterRef, Location
from app.models.project import Asset, Chapter, Frame, Project
from app.storage import asset_abs_path, project_dir, tmp_dir


def _session() -> Session:
    return Session(db.engine)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def slug_key(name: str) -> str:
    import unicodedata

    base = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    base = "".join(c for c in base if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "item"


def ensure_default_outfit(s: Session, character_id: str) -> None:
    """Ensure character has at least one default outfit."""
    outfits = s.exec(
        select(CharacterOutfit).where(CharacterOutfit.character_id == character_id)
    ).all()
    if not outfits:
        c = CharacterOutfit(
            character_id=character_id,
            key="default",
            name_vi="Mặc định",
            outfit_lock="",
            short_id="",
            is_default=True,
            sheet_status="missing",
        )
        s.add(c)
        s.commit()
    elif not any(o.is_default for o in outfits):
        outfits[0].is_default = True
        s.add(outfits[0])
        s.commit()


# ---------------------------------------------------------------------------
# Bible view (Project-level characters with outfits + locations)
# ---------------------------------------------------------------------------
def get_bible(pid: str) -> dict[str, Any]:
    with _session() as s:
        p = s.get(Project, pid)
        if not p:
            raise AppError("PROJECT_NOT_FOUND", "Không tìm thấy dự án", status_code=404)

        chars = s.exec(select(Character).where(Character.project_id == pid)).all()
        locations = s.exec(select(Location).where(Location.project_id == pid)).all()

        chars_out = []
        for c in chars:
            ensure_default_outfit(s, c.id)
            outfits = s.exec(
                select(CharacterOutfit).where(CharacterOutfit.character_id == c.id)
            ).all()
            outfits_sorted = sorted(outfits, key=lambda o: (not o.is_default, o.key))
            char_refs = s.exec(
                select(CharacterRef)
                .where(CharacterRef.character_id == c.id)
                .order_by(CharacterRef.order, CharacterRef.created_at)
            ).all()
            refs_out = [
                {
                    **r.model_dump(mode="json"),
                    "image_url": f"/api/assets/{r.asset_id}/file",
                }
                for r in char_refs
            ]
            chars_out.append(
                {
                    **c.model_dump(mode="json"),
                    "refs": refs_out,
                    "outfits": [
                        {
                            **o.model_dump(mode="json"),
                            "sheet_url": f"/api/assets/{o.sheet_asset_id}/file"
                            if o.sheet_asset_id
                            else None,
                        }
                        for o in outfits_sorted
                    ],
                }
            )

        locs_out = [
            {
                **loc.model_dump(mode="json"),
                "sheet_url": f"/api/assets/{loc.sheet_asset_id}/file"
                if loc.sheet_asset_id
                else None,
            }
            for loc in sorted(locations, key=lambda loc_item: loc_item.name_vi.casefold())
        ]

        return {
            "project_id": pid,
            "characters": sorted(
                chars_out, key=lambda c: (c.get("status") != "suggested", c["name"].casefold())
            ),
            "locations": locs_out,
        }


# ---------------------------------------------------------------------------
# Outfits CRUD
# ---------------------------------------------------------------------------
def list_outfits(chid: str) -> list[dict[str, Any]]:
    with _session() as s:
        c = s.get(Character, chid)
        if not c:
            raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)
        ensure_default_outfit(s, chid)
        outfits = s.exec(select(CharacterOutfit).where(CharacterOutfit.character_id == chid)).all()
        return [
            {
                **o.model_dump(mode="json"),
                "sheet_url": f"/api/assets/{o.sheet_asset_id}/file" if o.sheet_asset_id else None,
            }
            for o in sorted(outfits, key=lambda o: (not o.is_default, o.key))
        ]


def create_outfit(chid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        c = s.get(Character, chid)
        if not c:
            raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)

        raw_name = data.get("name_vi", "").strip() or "Trang phục"
        key = data.get("key") or slug_key(raw_name)
        existing = {
            o.key
            for o in s.exec(select(CharacterOutfit).where(CharacterOutfit.character_id == chid))
        }
        base, n = key, 2
        while key in existing:
            key = f"{base}_{n}"
            n += 1

        is_default = bool(data.get("is_default", False))
        if is_default:
            for o in s.exec(select(CharacterOutfit).where(CharacterOutfit.character_id == chid)):
                if o.is_default:
                    o.is_default = False
                    s.add(o)

        outfit = CharacterOutfit(
            character_id=chid,
            key=key,
            name_vi=raw_name,
            outfit_lock=data.get("outfit_lock") or "",
            short_id=data.get("short_id") or "",
            is_default=is_default,
            sheet_status="missing",
            note=data.get("note"),
        )
        s.add(outfit)
        s.commit()
        s.refresh(outfit)
        return {
            **outfit.model_dump(mode="json"),
            "sheet_url": None,
        }


def update_outfit(oid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        outfit = s.get(CharacterOutfit, oid)
        if not outfit:
            raise AppError("OUTFIT_NOT_FOUND", "Không tìm thấy trang phục", status_code=404)

        if data.get("is_default") is True and not outfit.is_default:
            for o in s.exec(
                select(CharacterOutfit).where(CharacterOutfit.character_id == outfit.character_id)
            ):
                if o.id != outfit.id and o.is_default:
                    o.is_default = False
                    s.add(o)
            outfit.is_default = True

        for k in ("name_vi", "outfit_lock", "short_id", "note"):
            if k in data and data[k] is not None:
                setattr(outfit, k, data[k].strip() if isinstance(data[k], str) else data[k])

        if data.get("key"):
            new_key = slug_key(data["key"])
            existing = {
                o.key
                for o in s.exec(
                    select(CharacterOutfit).where(
                        CharacterOutfit.character_id == outfit.character_id,
                        CharacterOutfit.id != outfit.id,
                    )
                )
            }
            if new_key in existing:
                raise AppError(
                    "OUTFIT_KEY_EXISTS", f"Mã trang phục '{new_key}' đã tồn tại", status_code=409
                )
            outfit.key = new_key

        s.add(outfit)
        s.commit()
        s.refresh(outfit)
        return {
            **outfit.model_dump(mode="json"),
            "sheet_url": f"/api/assets/{outfit.sheet_asset_id}/file"
            if outfit.sheet_asset_id
            else None,
        }


def delete_outfit(oid: str) -> dict[str, Any]:
    with _session() as s:
        outfit = s.get(CharacterOutfit, oid)
        if not outfit:
            raise AppError("OUTFIT_NOT_FOUND", "Không tìm thấy trang phục", status_code=404)

        all_outfits = s.exec(
            select(CharacterOutfit).where(CharacterOutfit.character_id == outfit.character_id)
        ).all()
        if len(all_outfits) <= 1:
            raise AppError(
                "CANNOT_DELETE_LAST_OUTFIT",
                "Nhân vật phải có ít nhất một trang phục",
                status_code=409,
            )

        if outfit.is_default:
            defaults = [o for o in all_outfits if o.is_default]
            if len(defaults) <= 1:
                raise AppError(
                    "CANNOT_DELETE_DEFAULT_OUTFIT",
                    "Không thể xóa trang phục mặc định cuối cùng",
                    status_code=409,
                )

        s.delete(outfit)
        s.commit()
        return {"deleted": oid}


# ---------------------------------------------------------------------------
# Locations CRUD
# ---------------------------------------------------------------------------
def list_locations(pid: str) -> list[dict[str, Any]]:
    with _session() as s:
        p = s.get(Project, pid)
        if not p:
            raise AppError("PROJECT_NOT_FOUND", "Không tìm thấy dự án", status_code=404)
        locs = s.exec(select(Location).where(Location.project_id == pid)).all()
        return [
            {
                **loc_item.model_dump(mode="json"),
                "sheet_url": f"/api/assets/{loc_item.sheet_asset_id}/file"
                if loc_item.sheet_asset_id
                else None,
            }
            for loc_item in sorted(locs, key=lambda x: x.name_vi.casefold())
        ]


def create_location(pid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        p = s.get(Project, pid)
        if not p:
            raise AppError("PROJECT_NOT_FOUND", "Không tìm thấy dự án", status_code=404)

        name_vi = data.get("name_vi", "").strip()
        if not name_vi:
            raise AppError("INVALID_LOCATION", "Tên bối cảnh không được để trống", status_code=422)

        key = data.get("key") or slug_key(name_vi)
        existing = {
            loc_row.key for loc_row in s.exec(select(Location).where(Location.project_id == pid))
        }
        base, n = key, 2
        while key in existing:
            key = f"{base}_{n}"
            n += 1

        loc = Location(
            project_id=pid,
            key=key,
            name_vi=name_vi,
            aliases=[a.strip() for a in data.get("aliases") or [] if a.strip()],
            location_lock=data.get("location_lock") or "",
            ref_frame_ids=data.get("ref_frame_ids") or [],
            sheet_status="missing",
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        return {
            **loc.model_dump(mode="json"),
            "sheet_url": None,
        }


def update_location(lid: str, data: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        loc = s.get(Location, lid)
        if not loc:
            raise AppError("LOCATION_NOT_FOUND", "Không tìm thấy bối cảnh", status_code=404)

        for k in ("name_vi", "location_lock"):
            if k in data and data[k] is not None:
                setattr(loc, k, data[k].strip() if isinstance(data[k], str) else data[k])

        if data.get("aliases") is not None:
            loc.aliases = [a.strip() for a in data["aliases"] if a.strip()]

        if data.get("ref_frame_ids") is not None:
            loc.ref_frame_ids = list(data["ref_frame_ids"])

        if data.get("key"):
            new_key = slug_key(data["key"])
            existing = {
                loc_row.key
                for loc_row in s.exec(
                    select(Location).where(
                        Location.project_id == loc.project_id,
                        Location.id != loc.id,
                    )
                )
            }
            if new_key in existing:
                raise AppError(
                    "LOCATION_KEY_EXISTS", f"Mã bối cảnh '{new_key}' đã tồn tại", status_code=409
                )
            loc.key = new_key

        s.add(loc)
        s.commit()
        s.refresh(loc)
        return {
            **loc.model_dump(mode="json"),
            "sheet_url": f"/api/assets/{loc.sheet_asset_id}/file" if loc.sheet_asset_id else None,
        }


def delete_location(lid: str) -> dict[str, Any]:
    with _session() as s:
        loc = s.get(Location, lid)
        if not loc:
            raise AppError("LOCATION_NOT_FOUND", "Không tìm thấy bối cảnh", status_code=404)
        s.delete(loc)
        s.commit()
        return {"deleted": lid}


# ---------------------------------------------------------------------------
# Frame suggestions
# ---------------------------------------------------------------------------
def suggest_frames(chid: str) -> list[dict[str, Any]]:
    with _session() as s:
        c = s.get(Character, chid)
        if not c:
            raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)

        chapter_ids = [
            ch.id for ch in s.exec(select(Chapter).where(Chapter.project_id == c.project_id))
        ]
        if not chapter_ids:
            return []

        all_frames = list(s.exec(select(Frame).where(Frame.chapter_id.in_(chapter_ids))))

        matched: list[Frame] = []
        for f in all_frames:
            r = f.reading or {}
            chars = r.get("characters") or []
            if c.key in chars:
                matched.append(f)

        # Prioritize frame_type == 'scene', then chapter, idx
        matched.sort(
            key=lambda f: (
                0 if f.frame_type == "scene" else 1,
                f.chapter_id,
                f.idx,
            )
        )

        return [
            {
                "id": f.id,
                "chapter_id": f.chapter_id,
                "idx": f.idx,
                "frame_type": f.frame_type,
                "image_url": f"/api/assets/{f.asset_id}/file",
            }
            for f in matched[:12]
        ]


# ---------------------------------------------------------------------------
# Sheet Bundle & Upload (Shared for Outfit and Location)
# ---------------------------------------------------------------------------
TargetType = Literal["outfits", "locations"]

CHARACTER_SHEET_TEMPLATE = (
    "Create a professional character turnaround sheet of the SAME character "
    "shown in the attached comic panels.\n\n"
    "Layout on a plain light-grey background, 16:9:\n"
    "- top row: full body front view, 3/4 view, side view, back view "
    "(same scale, standing neutral pose, arms slightly away from body)\n"
    "- bottom row: large face close-up front, face close-up 3/4, "
    "and 2 detail callouts of the outfit/accessories\n"
    "Character: {char_desc}\n"
    "Style: 2D anime cel-shaded, clean line art matching the source manhua, "
    "flat even lighting, no shadows on background.\n"
    "Keep the face, hairstyle, eye colour, outfit and colours exactly as in the panels. "
    "Do not invent new accessories.\n"
    "No text, no labels, no speech bubbles, no watermark."
)

LOCATION_SHEET_TEMPLATE = (
    "Create a professional location reference sheet of the SAME location "
    "shown in the attached comic panels.\n\n"
    "Layout on a plain light-grey background, 16:9:\n"
    "- establishing wide shot + reverse angle, no characters\n"
    "Location: {loc_desc}\n"
    "Style: 2D anime cel-shaded, clean line art matching the source manhua, "
    "flat even lighting, no shadows on background.\n"
    "Keep architectural style, materials, colour palette and lighting consistent with the panels.\n"
    "No text, no labels, no speech bubbles, no watermark."
)

HUONG_DAN_TEXT = (
    "Giải nén (Extract All) trước khi kéo ảnh vào Gemini — "
    "kéo thẳng từ file zip sẽ bị lỗi tải lên. Mỗi gói dùng một cuộc chat MỚI.\n"
    "Hướng dẫn tạo Sheet nhất quán bằng Gemini:\n"
    "1. Mở app Gemini (hoặc web Gemini).\n"
    "2. Đính kèm các ảnh tham chiếu trong gói này theo đúng thứ tự (01_..., 02_...).\n"
    "3. Dán toàn bộ nội dung trong file prompt.txt vào ô chat.\n"
    "4. Chạy tạo ảnh 2–4 lần để chọn ảnh tốt nhất (rõ nét, đúng đặc điểm).\n"
    "5. Tải ảnh tốt nhất về máy và thả vào app Comic Film Studio để lưu và duyệt."
)


def get_sheet_bundle(target: TargetType, item_id: str) -> tuple[bytes, str]:
    with _session() as s:
        if target == "outfits":
            outfit = s.get(CharacterOutfit, item_id)
            if not outfit:
                raise AppError("OUTFIT_NOT_FOUND", "Không tìm thấy trang phục", status_code=404)
            char = s.get(Character, outfit.character_id)
            if not char:
                raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)
            if char.is_group:
                raise AppError(
                    "GROUP_HAS_NO_SHEET",
                    "Nhân vật nhóm không dùng sheet nhất quán",
                    status_code=400,
                )
            pid = char.project_id

            refs = s.exec(select(CharacterRef).where(CharacterRef.character_id == char.id)).all()
            if not refs:
                raise AppError(
                    "REF_IMAGES_REQUIRED",
                    "Cần có ít nhất 1 ảnh tham chiếu cho nhân vật trước",
                    status_code=409,
                )

            sorted_refs = sorted(
                refs,
                key=lambda r: (r.outfit_id != outfit.id, r.order, r.created_at),
            )

            parts = []
            if char.look_lock and char.look_lock.strip():
                parts.append(char.look_lock.strip())
            if outfit.outfit_lock and outfit.outfit_lock.strip():
                parts.append(outfit.outfit_lock.strip())
            char_desc = ", ".join(parts) if parts else char.name

            prompt_content = CHARACTER_SHEET_TEMPLATE.format(char_desc=char_desc)
            zip_filename = f"sheet_bundle_char_{char.key}_{outfit.key}.zip"

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("prompt.txt", prompt_content.encode("utf-8"))
                zf.writestr("HUONG_DAN.txt", HUONG_DAN_TEXT.encode("utf-8"))

                for idx, r in enumerate(sorted_refs, 1):
                    asset = s.get(Asset, r.asset_id)
                    if asset:
                        abs_p = asset_abs_path(pid, asset.path)
                        if abs_p.is_file():
                            img_bytes = _jpeg_bytes(abs_p, max_side=1600, quality=85)
                            zf.writestr(f"{idx:02d}_{r.id}.jpg", img_bytes)

            return buf.getvalue(), zip_filename

        elif target == "locations":
            loc = s.get(Location, item_id)
            if not loc:
                raise AppError("LOCATION_NOT_FOUND", "Không tìm thấy bối cảnh", status_code=404)
            pid = loc.project_id
            ref_frame_ids = loc.ref_frame_ids or []
            if not ref_frame_ids:
                raise AppError(
                    "REF_FRAMES_REQUIRED", "Chọn 2–4 khung tham chiếu trước", status_code=409
                )

            loc_desc = (loc.location_lock or "").strip() or loc.name_vi
            prompt_content = LOCATION_SHEET_TEMPLATE.format(loc_desc=loc_desc)
            zip_filename = f"sheet_bundle_location_{loc.key}.zip"

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("prompt.txt", prompt_content.encode("utf-8"))
                zf.writestr("HUONG_DAN.txt", HUONG_DAN_TEXT.encode("utf-8"))

                for idx, fid in enumerate(ref_frame_ids, 1):
                    frame = s.get(Frame, fid)
                    if frame:
                        asset = s.get(Asset, frame.asset_id)
                        if asset:
                            abs_p = asset_abs_path(pid, asset.path)
                            if abs_p.is_file():
                                img_bytes = _jpeg_bytes(abs_p, max_side=1600, quality=85)
                                zf.writestr(f"{idx:02d}_{fid}.jpg", img_bytes)

            return buf.getvalue(), zip_filename
        else:
            raise AppError("INVALID_TARGET", f"Mục tiêu '{target}' không hợp lệ", status_code=400)


def _sheet_assets(s: Session, pid: str, kind: str, rel_base: str) -> list[Asset]:
    """Find all assets belonging strictly to this sheet directory: <rel_base>/..."""
    prefix = rel_base.rstrip("/") + "/"
    all_kind = s.exec(
        select(Asset).where(
            Asset.project_id == pid,
            Asset.kind == kind,
        )
    ).all()
    return [a for a in all_kind if a.path.startswith(prefix)]


def upload_sheet(target: TargetType, item_id: str, file_bytes: bytes) -> dict[str, Any]:
    # Write temp file and check image
    t_dir = tmp_dir()
    temp_path = t_dir / f"upload_sheet_{uuid4().hex}.img"
    try:
        temp_path.write_bytes(file_bytes)
        check = check_image(temp_path, min_width=100)
        if not check.ok:
            raise AppError(
                "INVALID_IMAGE", check.reason or "Ảnh không hợp lệ hoặc bị hỏng", status_code=422
            )

        with _session() as s:
            if target == "outfits":
                outfit = s.get(CharacterOutfit, item_id)
                if not outfit:
                    raise AppError("OUTFIT_NOT_FOUND", "Không tìm thấy trang phục", status_code=404)
                char = s.get(Character, outfit.character_id)
                if not char:
                    raise AppError(
                        "CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404
                    )
                if char.is_group:
                    raise AppError(
                        "GROUP_HAS_NO_SHEET",
                        "Nhân vật nhóm không dùng sheet nhất quán",
                        status_code=400,
                    )
                pid = char.project_id
                kind = "char_sheet"
                rel_base = f"refs/{char.key}/{outfit.key}"
                current_asset_id = outfit.sheet_asset_id
            elif target == "locations":
                loc = s.get(Location, item_id)
                if not loc:
                    raise AppError("LOCATION_NOT_FOUND", "Không tìm thấy bối cảnh", status_code=404)
                pid = loc.project_id
                kind = "location_sheet"
                rel_base = f"locations/{loc.key}"
                current_asset_id = loc.sheet_asset_id
            else:
                raise AppError(
                    "INVALID_TARGET", f"Mục tiêu '{target}' không hợp lệ", status_code=400
                )

            target_folder = project_dir(pid) / rel_base
            target_folder.mkdir(parents=True, exist_ok=True)

            # Determine next version
            versions = [1]
            existing_assets = _sheet_assets(s, pid, kind, rel_base)
            for a in existing_assets:
                versions.append(a.version + 1)
            for p in target_folder.glob("sheet_v*.png"):
                m = re.search(r"sheet_v(\d+)\.png$", p.name)
                if m:
                    versions.append(int(m.group(1)) + 1)
            next_version = max(versions)

            rel_path = f"{rel_base}/sheet_v{next_version}.png"
            final_abs_path = asset_abs_path(pid, rel_path)
            final_abs_path.parent.mkdir(parents=True, exist_ok=True)
            final_abs_path.write_bytes(file_bytes)

            asset = Asset(
                project_id=pid,
                kind=kind,
                path=rel_path,
                sha256=check.sha256,
                version=next_version,
                parent_ids=[current_asset_id] if current_asset_id else [],
                approval="pending",
                media={"width": check.width, "height": check.height},
            )
            s.add(asset)
            s.flush()

            if target == "outfits":
                outfit.sheet_asset_id = asset.id
                outfit.sheet_status = "pending"
                s.add(outfit)
                s.commit()
                s.refresh(outfit)
                return {
                    **outfit.model_dump(mode="json"),
                    "sheet_url": f"/api/assets/{asset.id}/file",
                }
            else:
                loc.sheet_asset_id = asset.id
                loc.sheet_status = "pending"
                s.add(loc)
                s.commit()
                s.refresh(loc)
                return {
                    **loc.model_dump(mode="json"),
                    "sheet_url": f"/api/assets/{asset.id}/file",
                }
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def approve_sheet(target: TargetType, item_id: str) -> dict[str, Any]:
    with _session() as s:
        if target == "outfits":
            item = s.get(CharacterOutfit, item_id)
            if not item:
                raise AppError("OUTFIT_NOT_FOUND", "Không tìm thấy trang phục", status_code=404)
        elif target == "locations":
            item = s.get(Location, item_id)
            if not item:
                raise AppError("LOCATION_NOT_FOUND", "Không tìm thấy bối cảnh", status_code=404)
        else:
            raise AppError("INVALID_TARGET", f"Mục tiêu '{target}' không hợp lệ", status_code=400)

        item.sheet_status = "approved"
        if item.sheet_asset_id:
            asset = s.get(Asset, item.sheet_asset_id)
            if asset:
                asset.approval = "approved"
                s.add(asset)
        s.add(item)
        s.commit()
        s.refresh(item)
        return {
            **item.model_dump(mode="json"),
            "sheet_url": f"/api/assets/{item.sheet_asset_id}/file" if item.sheet_asset_id else None,
        }


def reject_sheet(target: TargetType, item_id: str) -> dict[str, Any]:
    with _session() as s:
        if target == "outfits":
            item = s.get(CharacterOutfit, item_id)
            if not item:
                raise AppError("OUTFIT_NOT_FOUND", "Không tìm thấy trang phục", status_code=404)
            char = s.get(Character, item.character_id)
            pid = char.project_id if char else ""
            rel_base = f"refs/{char.key}/{item.key}" if char else ""
            kind = "char_sheet"
        elif target == "locations":
            item = s.get(Location, item_id)
            if not item:
                raise AppError("LOCATION_NOT_FOUND", "Không tìm thấy bối cảnh", status_code=404)
            pid = item.project_id
            rel_base = f"locations/{item.key}"
            kind = "location_sheet"
        else:
            raise AppError("INVALID_TARGET", f"Mục tiêu '{target}' không hợp lệ", status_code=400)

        if item.sheet_asset_id:
            asset = s.get(Asset, item.sheet_asset_id)
            if asset:
                asset.approval = "rejected"
                s.add(asset)

        # Check if an earlier approved asset exists for this item
        matching = [
            a
            for a in _sheet_assets(s, pid, kind, rel_base)
            if a.approval == "approved" and a.id != item.sheet_asset_id
        ]
        if matching:
            latest = max(matching, key=lambda a: a.version)
            item.sheet_asset_id = latest.id
            item.sheet_status = "approved"
        else:
            item.sheet_status = "missing"

        s.add(item)
        s.commit()
        s.refresh(item)
        return {
            **item.model_dump(mode="json"),
            "sheet_url": f"/api/assets/{item.sheet_asset_id}/file"
            if item.sheet_asset_id and item.sheet_status == "approved"
            else None,
        }


# ---------------------------------------------------------------------------
# Character References (Phase 2b1)
# ---------------------------------------------------------------------------
def _next_ref_path(s: Session, pid: str, char_key: str) -> tuple[str, Path]:
    target_folder = project_dir(pid) / "refs" / char_key / "refs"
    target_folder.mkdir(parents=True, exist_ok=True)
    existing_nums = [0]
    for p in target_folder.glob("ref_*.jpg"):
        m = re.search(r"ref_(\d+)\.jpg$", p.name)
        if m:
            existing_nums.append(int(m.group(1)))
    existing_assets = s.exec(
        select(Asset).where(
            Asset.project_id == pid,
            Asset.kind == "char_ref",
        )
    ).all()
    prefix = f"refs/{char_key}/refs/ref_"
    for a in existing_assets:
        if a.path.startswith(prefix) and a.path.endswith(".jpg"):
            m = re.search(r"ref_(\d+)\.jpg$", a.path)
            if m:
                existing_nums.append(int(m.group(1)))
    next_num = max(existing_nums) + 1
    rel_path = f"refs/{char_key}/refs/ref_{next_num}.jpg"
    abs_path = asset_abs_path(pid, rel_path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    return rel_path, abs_path


def create_character_ref_from_crop(
    chid: str,
    frame_id: str,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    outfit_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    with _session() as s:
        char = s.get(Character, chid)
        if not char:
            raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)
        frame = s.get(Frame, frame_id)
        if not frame:
            raise AppError("FRAME_NOT_FOUND", "Không tìm thấy khung ảnh", status_code=404)
        asset = s.get(Asset, frame.asset_id)
        if not asset:
            raise AppError("ASSET_NOT_FOUND", "Không tìm thấy file ảnh khung", status_code=404)
        abs_p = asset_abs_path(char.project_id, asset.path)
        if not abs_p.is_file():
            raise AppError(
                "ASSET_NOT_FOUND", "File ảnh khung không tồn tại trên đĩa", status_code=404
            )

        try:
            with Image.open(abs_p) as im:
                W, H = im.size
                if x0 < 0 or y0 < 0 or x1 > W or y1 > H or x0 >= x1 or y0 >= y1:
                    raise AppError(
                        "INVALID_CROP",
                        f"Tọa độ crop ngoài biên ảnh ({W}x{H})",
                        status_code=422,
                    )
                cw, ch_dim = x1 - x0, y1 - y0
                if cw < 64 or ch_dim < 64:
                    raise AppError(
                        "INVALID_CROP",
                        f"Kích thước crop quá nhỏ ({cw}x{ch_dim} < 64x64)",
                        status_code=422,
                    )
                cropped = im.crop((x0, y0, x1, y1)).convert("RGB")
                max_side = max(cropped.size)
                if max_side > 1600:
                    scale = 1600 / max_side
                    new_w = max(1, round(cropped.width * scale))
                    new_h = max(1, round(cropped.height * scale))
                    cropped = cropped.resize((new_w, new_h), Image.LANCZOS)

                rel_path, abs_path = _next_ref_path(s, char.project_id, char.key)
                cropped.save(abs_path, "JPEG", quality=85)
        except AppError:
            raise
        except Exception as e:
            raise AppError("CROP_FAILED", f"Lỗi cắt ảnh: {e}", status_code=422) from e

        sha = sha256_file(abs_path)
        ref_asset = Asset(
            project_id=char.project_id,
            kind="char_ref",
            path=rel_path,
            sha256=sha,
            approval="approved",
            media={"width": cropped.width, "height": cropped.height},
        )
        s.add(ref_asset)
        s.flush()

        cur_refs = s.exec(select(CharacterRef).where(CharacterRef.character_id == char.id)).all()
        next_order = max((r.order for r in cur_refs), default=0) + 1

        ref = CharacterRef(
            character_id=char.id,
            outfit_id=outfit_id,
            asset_id=ref_asset.id,
            source_frame_id=frame.id,
            crop={"x0": x0, "y0": y0, "x1": x1, "y1": y1},
            note=note,
            order=next_order,
        )
        s.add(ref)
        s.commit()
        s.refresh(ref)
        return {
            **ref.model_dump(mode="json"),
            "image_url": f"/api/assets/{ref_asset.id}/file",
        }


def create_character_ref_from_upload(
    chid: str,
    file_bytes: bytes,
    outfit_id: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    t_dir = tmp_dir()
    temp_path = t_dir / f"upload_ref_{uuid4().hex}.img"
    try:
        temp_path.write_bytes(file_bytes)
        check = check_image(temp_path, min_width=64)
        if not check.ok:
            raise AppError(
                "INVALID_IMAGE", check.reason or "Ảnh không hợp lệ hoặc bị hỏng", status_code=422
            )

        with _session() as s:
            char = s.get(Character, chid)
            if not char:
                raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)

            with Image.open(temp_path) as im:
                im = im.convert("RGB")
                max_side = max(im.size)
                if max_side > 1600:
                    scale = 1600 / max_side
                    new_w = max(1, round(im.width * scale))
                    new_h = max(1, round(im.height * scale))
                    im = im.resize((new_w, new_h), Image.LANCZOS)

                rel_path, abs_path = _next_ref_path(s, char.project_id, char.key)
                im.save(abs_path, "JPEG", quality=85)

            sha = sha256_file(abs_path)
            ref_asset = Asset(
                project_id=char.project_id,
                kind="char_ref",
                path=rel_path,
                sha256=sha,
                approval="approved",
                media={"width": im.width, "height": im.height},
            )
            s.add(ref_asset)
            s.flush()

            cur_refs = s.exec(
                select(CharacterRef).where(CharacterRef.character_id == char.id)
            ).all()
            next_order = max((r.order for r in cur_refs), default=0) + 1

            ref = CharacterRef(
                character_id=char.id,
                outfit_id=outfit_id,
                asset_id=ref_asset.id,
                source_frame_id=None,
                crop=None,
                note=note,
                order=next_order,
            )
            s.add(ref)
            s.commit()
            s.refresh(ref)
            return {
                **ref.model_dump(mode="json"),
                "image_url": f"/api/assets/{ref_asset.id}/file",
            }
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def list_character_refs(chid: str) -> list[dict[str, Any]]:
    with _session() as s:
        char = s.get(Character, chid)
        if not char:
            raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)
        refs = s.exec(
            select(CharacterRef)
            .where(CharacterRef.character_id == chid)
            .order_by(CharacterRef.order, CharacterRef.created_at)
        ).all()
        return [
            {
                **r.model_dump(mode="json"),
                "image_url": f"/api/assets/{r.asset_id}/file",
            }
            for r in refs
        ]


def delete_character_ref(rid: str) -> dict[str, Any]:
    with _session() as s:
        ref = s.get(CharacterRef, rid)
        if not ref:
            raise AppError("REF_NOT_FOUND", "Không tìm thấy ảnh tham chiếu", status_code=404)
        s.delete(ref)
        s.commit()
        return {"deleted": rid}


def update_character_ref(rid: str, patch: dict[str, Any]) -> dict[str, Any]:
    with _session() as s:
        ref = s.get(CharacterRef, rid)
        if not ref:
            raise AppError("REF_NOT_FOUND", "Không tìm thấy ảnh tham chiếu", status_code=404)
        if "outfit_id" in patch:
            ref.outfit_id = patch["outfit_id"]
        if "order" in patch and patch["order"] is not None:
            ref.order = patch["order"]
        if "note" in patch:
            ref.note = patch["note"]
        s.add(ref)
        s.commit()
        s.refresh(ref)
        return {
            **ref.model_dump(mode="json"),
            "image_url": f"/api/assets/{ref.asset_id}/file",
        }


def enqueue_look_profile(chid: str) -> dict[str, Any]:
    with _session() as s:
        char = s.get(Character, chid)
        if not char:
            raise AppError("CHARACTER_NOT_FOUND", "Không tìm thấy nhân vật", status_code=404)
        refs = s.exec(select(CharacterRef).where(CharacterRef.character_id == chid)).all()
        if not refs:
            raise AppError(
                "NO_REF_IMAGES", "Nhân vật cần có ít nhất 1 ảnh tham chiếu", status_code=400
            )
    job = job_service.enqueue("character_profile", {"character_id": chid})
    return {"job_id": job.id, "job": job.model_dump(mode="json")}
