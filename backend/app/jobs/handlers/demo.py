import asyncio
import time

from app.jobs.registry import JobContext, JobError, job_handler


@job_handler("demo_sleep")
async def handle_demo_sleep(ctx: JobContext) -> None:
    """Async demo job — simulates non-blocking async work."""
    duration = int(ctx.payload.get("duration_s", 5))
    fail = bool(ctx.payload.get("fail", False))
    fail_category = str(ctx.payload.get("fail_category", "transient"))
    fail_message = str(ctx.payload.get("fail_message", "Mô phỏng lỗi tiến trình demo"))

    ctx.log(f"Bắt đầu job demo_sleep, thời gian chạy: {duration}s")

    for i in range(1, duration + 1):
        if ctx.is_cancelled():
            ctx.log("Job demo_sleep nhận được yêu cầu hủy, dừng xử lý.")
            return
        await asyncio.sleep(1)
        progress = i / max(1, duration)
        ctx.report_progress(progress, f"Đang xử lý bước {i}/{duration}")

    if fail:
        ctx.log(f"Ném lỗi thử nghiệm category={fail_category}: {fail_message}")
        raise JobError(category=fail_category, message=fail_message)

    ctx.log("Hoàn thành job demo_sleep thành công.")


@job_handler("demo_cpu")
def handle_demo_cpu(ctx: JobContext) -> None:
    """Sync (CPU-bound) demo job — runs in asyncio.to_thread so it does NOT block the event loop.

    Verifies B2: while this handler is running (using time.sleep to simulate
    CPU work), the event loop remains free and /api/health still responds in < 200ms.
    """
    duration = int(ctx.payload.get("duration_s", 5))
    fail = bool(ctx.payload.get("fail", False))
    fail_category = str(ctx.payload.get("fail_category", "permanent"))
    fail_message = str(ctx.payload.get("fail_message", "Mô phỏng lỗi CPU demo"))

    ctx.log(f"Bắt đầu job demo_cpu (sync), thời gian mô phỏng: {duration}s")

    for i in range(1, duration + 1):
        if ctx.is_cancelled():
            ctx.log("Job demo_cpu nhận được yêu cầu hủy, dừng xử lý.")
            return
        # time.sleep in a thread does NOT block the event loop
        time.sleep(1)
        progress = i / max(1, duration)
        ctx.report_progress(progress, f"Đang xử lý CPU bước {i}/{duration}")

    if fail:
        ctx.log(f"Ném lỗi thử nghiệm category={fail_category}: {fail_message}")
        raise JobError(category=fail_category, message=fail_message)

    ctx.log("Hoàn thành job demo_cpu thành công.")
