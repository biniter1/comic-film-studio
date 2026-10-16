"""Phase 1 job handlers. All `def` → run in a worker thread (SPEC §5.6)."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.config import settings
from app.errors import AppError
from app.importer import url as urlimp
from app.jobs.registry import JobContext, JobError, job_handler
from app.services import studio
from app.storage import resolve_safe_path, tmp_dir

FOLDER_HINT = "Hãy dùng 'Nhập từ thư mục': tải ảnh về máy rồi kéo-thả vào app."


def _upload_dir(upload_id: str):
    return resolve_safe_path(tmp_dir(settings.data_dir), upload_id)


@job_handler("import_local")
def handle_import_local(ctx: JobContext) -> None:
    cid = ctx.payload["chapter_id"]
    up = _upload_dir(ctx.payload["upload_id"])
    manifest = up / "manifest.json"
    if not manifest.exists():
        raise JobError("permanent", "Không tìm thấy file tải lên (có thể đã bị dọn). Hãy tải lại.")
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    items = [(e["name"], up / e["file"]) for e in entries if e.get("file")]
    pre_rejected = [{"name": e["name"], "reason": e["error"]} for e in entries if e.get("error")]
    ctx.log(f"Nhập {len(items)} file vào chapter {cid}")
    try:
        report = studio.ingest_images(cid, items, ctx.report_progress, pre_rejected)
    except AppError as e:
        raise JobError("permanent", e.message_vi) from e
    _log_report(ctx, report)
    shutil.rmtree(up, ignore_errors=True)
    if not report["added"] and not report["duplicates"]:
        raise JobError(
            "permanent", "Không có ảnh hợp lệ nào được nhập", "Xem danh sách file bị từ chối"
        )


@job_handler("import_url")
def handle_import_url(ctx: JobContext) -> None:
    cid = ctx.payload["chapter_id"]
    url = ctx.payload["url"]
    try:
        url = urlimp.validate_url(url)
    except urlimp.UnsafeUrlError as e:
        raise JobError("permanent", str(e)) from e

    work = tmp_dir(settings.data_dir) / f"url_{ctx.job_id}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        with urlimp.make_client() as client:
            ctx.report_progress(0.02, "Đang tải trang chapter")
            try:
                final_url, html = urlimp.fetch_chapter_html(client, url)
            except urlimp.FetchError as e:
                raise JobError(
                    "permanent" if e.permanent else "transient",
                    e.message_vi,
                    FOLDER_HINT if e.permanent else None,
                ) from e
            except urlimp.UnsafeUrlError as e:
                raise JobError("permanent", str(e)) from e
            except Exception as e:  # network errors (DNS, timeout, reset)
                raise JobError("transient", f"Lỗi mạng khi tải trang: {type(e).__name__}") from e

            profile = urlimp.match_profile(final_url, urlimp.load_profiles())
            img_urls = urlimp.extract_image_urls(html, final_url, profile)
            ctx.log(
                f"Profile: {profile.domain if profile else '(chung)'}; tìm thấy {len(img_urls)} ảnh"
            )
            if not img_urls:
                raise JobError(
                    "permanent",
                    "Không tìm thấy ảnh nào trong trang (trang có thể tải ảnh bằng JavaScript "
                    "hoặc cần đăng nhập).",
                    FOLDER_HINT,
                )
            referer = final_url if (profile is None or profile.referer) else None
            items: list[tuple[str, object]] = []
            failed: list[dict[str, str]] = []

            def fetch(i: int, u: str):
                dest = work / f"{i:04d}.img"
                urlimp.download_image(client, u, referer, dest)
                return i, u, dest

            done = 0
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(_retry, fetch, i, u) for i, u in enumerate(img_urls, 1)]
                for fut in as_completed(futures):
                    if ctx.is_cancelled():
                        for f in futures:
                            f.cancel()
                        return
                    i, u, dest, err = fut.result()
                    done += 1
                    if err:
                        failed.append({"name": u, "reason": err})
                    else:
                        items.append((f"{i:04d}_{u.rsplit('/', 1)[-1][:80]}", dest))
                    ctx.report_progress(
                        0.05 + 0.6 * done / len(img_urls), f"Đã tải {done}/{len(img_urls)} ảnh"
                    )
            if not items:
                raise JobError("permanent", "Không tải được ảnh nào từ trang.", FOLDER_HINT)

        def sub_progress(p: float, msg: str | None) -> None:
            ctx.report_progress(0.65 + 0.35 * p, msg)

        report = studio.ingest_images(cid, items, sub_progress, failed)  # type: ignore[arg-type]
        _log_report(ctx, report)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _retry(fn, i: int, u: str, attempts: int = 3):
    import time

    last = ""
    for k in range(attempts):
        try:
            _, _, dest = fn(i, u)
            return i, u, dest, None
        except urlimp.FetchError as e:
            last = e.message_vi
            if e.permanent:
                break
        except urlimp.UnsafeUrlError as e:
            return i, u, None, str(e)
        except Exception as e:  # network
            last = f"Lỗi mạng: {type(e).__name__}"
        time.sleep(0.5 * (2**k))
    return i, u, None, last


@job_handler("stitch_and_cut")
def handle_stitch_and_cut(ctx: JobContext) -> None:
    cid = ctx.payload["chapter_id"]
    try:
        n = studio.auto_frames(cid, ctx.report_progress)
    except AppError as e:
        raise JobError("permanent", e.message_vi) from e
    ctx.log(f"Đã cắt {n} khung")


def _log_report(ctx: JobContext, report: dict) -> None:
    ctx.log(
        f"Kết quả: thêm {len(report['added'])}, từ chối {len(report['rejected'])}, "
        f"trùng {len(report['duplicates'])}"
    )
    for r in report["rejected"]:
        ctx.log(f"  ✗ {r['name']}: {r['reason']}")
