# Review Phase 0 — PR #1 (đã merge) · Tech lead: Claude · 16/10/2026

## Tổng quan
Khung dự án tốt: cấu trúc đúng SPEC, test rõ ràng, chạy được trên Windows, kiểm tra thực tế (tắt/mở lại app khi job đang chạy) có làm và ghi lại. Lint/format/pytest (19 test) và `npm run lint/build` đều pass khi tech lead chạy lại trên Linux.

Tuy nhiên review tìm ra **4 lỗi thật** (đã viết test tái hiện, cả 4 đều fail trên code hiện tại) và 1 lỗ hổng thiết kế
mà Phase 1 sẽ đụng ngay. PR #1 đã merge, nên sửa trong **branch mới `phase-0-fixes`** → PR mới. Phải xong trước khi bắt đầu Phase 1.

---

## 🔴 Bắt buộc sửa

### B1. Sự kiện SSE bị mất khi gọi từ endpoint `def` (đồng bộ)
- `JobService._publish_job_updated` / `JobRunner._emit_job_event` dùng `asyncio.get_running_loop()`. Endpoint `def` của FastAPI chạy trong threadpool → không có loop → `RuntimeError` → **nuốt im lặng**.
- Hậu quả: tạo job, retry, hủy job đang `queued` **không** đẩy sự kiện → UI không cập nhật. (Test demo trên UI vẫn "chạy" vì sự kiện `running` phát từ worker.)
- Tái hiện:
  ```python
  q = event_bus.subscribe()
  await asyncio.to_thread(svc.enqueue, "demo_sleep", {"duration_s": 1})
  await asyncio.sleep(0.2); assert q.qsize() == 1   # FAIL: 0
  ```
- Sửa: `EventBus` lưu loop chính lúc startup (`event_bus.bind_loop(asyncio.get_running_loop())` trong lifespan); thêm `publish_threadsafe(event, data)` dùng `loop.call_soon_threadsafe(...)`, gọi được từ **mọi** thread. Mọi chỗ phát sự kiện dùng hàm này.

### B2. Handler đồng bộ (CPU/IO nặng) — cần ngay cho Phase 1
- Phase 1 có `stitch_and_cut` (Pillow/numpy, chapter 60.000px+), sau đó là ffmpeg. Chạy trong `async def` sẽ **chặn event loop** → API và SSE đứng hình trong lúc xử lý.
- Sửa: `@job_handler` chấp nhận cả `def`; runner phát hiện (`inspect.iscoroutinefunction`) và chạy handler `def` bằng `asyncio.to_thread`. `JobContext.report_progress/log/is_cancelled` phải an toàn khi gọi từ thread (ghi DB bằng session riêng — đã đúng; phát sự kiện qua `publish_threadsafe` của B1).
- Thêm handler demo `demo_cpu` (`def`, `time.sleep` + progress) và test: trong lúc nó chạy, `GET /api/health` vẫn trả lời < 200ms.

### B3. Job phụ thuộc vào job đã lỗi bị kẹt `queued` mãi mãi, không giải thích
- Tái hiện: cha `failed (permanent)` → con ở `queued` vĩnh viễn, `user_action_required = None`.
- Sửa theo SPEC §5.6 (đã cập nhật): cha `failed`/`cancelled` → con giữ `queued` + `user_action_required="Chờ job <id> được sửa hoặc chạy lại"` + phát sự kiện; cha chạy lại thành công → xóa thông báo. `depends_on` chứa id không tồn tại → con `failed/permanent`. Kiểm tra tồn tại ngay trong `enqueue` (lỗi 422).

### B4. Hủy job trong lúc chờ retry (backoff) bị bỏ qua + chiếm slot
- Tái hiện: job lỗi `transient`, đang `await asyncio.sleep(delay)` với `status=running` → gọi hủy → sau backoff vẫn bị đưa lại `queued` và chạy tiếp; `finally` xóa cờ hủy. Trong lúc chờ 30s nó còn **giữ 1 slot** concurrency.
- Sửa (SPEC §5.6 đã cập nhật): thêm cột `next_run_at` (**migration Alembic mới**). Lỗi transient → `status=queued`, `next_run_at=now+delay`, kết thúc task ngay. Worker chỉ lấy job `next_run_at IS NULL OR next_run_at <= now`. Hủy job `queued` (kể cả đang chờ backoff) → `cancelled` ngay.

### B5. Lỗ hổng đọc file tùy ý qua route phục vụ frontend
- `serve_spa` nối `dist_dir / full_path` không kiểm tra → `GET /..%2f..%2fbackend%2fpyproject.toml` trả về **200 + nội dung file**. Với đủ `../` có thể đọc `secrets.env` hoặc bất kỳ file nào user chạy app có quyền đọc.
- Sửa: resolve rồi kiểm tra nằm trong `dist_dir` (dùng lại `resolve_safe_path`), nếu không → trả `index.html`. Dùng `StaticFiles(directory=dist/assets)` cho `/assets`.
- Kèm: `GET /api/<không tồn tại>` hiện trả `index.html` 200 → phải trả **404 JSON** đúng format lỗi SPEC §9 (route SPA không được nuốt tiền tố `/api`).
- Test: 2 URL traversal ở trên → không trả nội dung file ngoài `dist`; `/api/khong-ton-tai` → 404 + `{"error": {...}}`.

### B6. Migration Alembic không được dùng
- `init_db()` gọi `SQLModel.metadata.create_all` → Alembic chỉ để trang trí. Từ Phase 1 thêm bảng/cột, DB cũ trên máy người dùng sẽ **không** được nâng cấp (create_all không ALTER).
- Sửa: khởi động app chạy `alembic upgrade head` bằng API (`alembic.command.upgrade(Config(...), "head")`), đường dẫn `alembic.ini` tính từ package (không phụ thuộc cwd). Test có thể giữ `create_all`, nhưng thêm 1 test: DB trống → upgrade head → có đủ bảng/cột như model (so `inspect`).
- `migrations/env.py` đang dùng `engine` toàn cục — cho phép truyền URL/engine qua `config.attributes` để test được.

---

## 🟡 Nên sửa (làm luôn trong PR này, đều nhỏ)
- **N1.** `_run_loop` có `except Exception: pass` → lỗi worker biến mất. Log `exception` (kèm traceback) vào log app.
- **N2.** Frontend `useEvents`: khi `onopen` (kể cả **kết nối lại**) → `invalidateQueries({queryKey: ["jobs"]})` để đồng bộ các sự kiện bị lỡ lúc mất kết nối.
- **N3.** `setQueriesData` cập nhật **mọi** danh sách `["jobs", …]` kể cả danh sách đang lọc → job `succeeded` bị chèn vào danh sách lọc `failed`. Chỉ chèn nếu khớp bộ lọc của query đó (hoặc invalidate danh sách lọc).
- **N4.** `progress_callback` ghi DB + phát sự kiện mỗi lần gọi → throttle (≤ 4 lần/giây, luôn ghi lần cuối) vì Phase 1 sẽ báo tiến độ theo từng ảnh.
- **N5.** Thêm `scripts/doctor.py` như PR đề xuất (kiểm tra Python 3.12/uv/Node/ffmpeg/git, in hướng dẫn cài bằng `winget`). ✅ Đồng ý.

## 🟢 Ghi chú (để sau)
- Session SQLAlchemy đồng bộ trong hàm async: chấp nhận được cho SQLite local, xem lại nếu thấy giật.
- Job id `J` + 6 hex: đủ dùng.

---

## Trả lời câu hỏi trong PR
1. **Payload có chứa secret không?** Quy ước: payload **chỉ** chứa ID và tham số kỹ thuật, không bao giờ chứa secret (đã ghi vào SPEC §5.6). Thêm kiểm tra trong `enqueue`: từ chối payload có khóa chứa `key`, `token`, `secret`, `password` (không phân biệt hoa thường) → lỗi lập trình, raise `ValueError`.
2. **Thiếu ffmpeg ở các phase sau?** Phase 1 **không** cần ffmpeg (chỉ Pillow). Từ Phase 3: endpoint cần ffmpeg kiểm tra trước → **409 `FFMPEG_MISSING`** + `message_vi` hướng dẫn cài; handler vẫn kiểm tra lại (phòng thủ) → `failed/permanent` + `user_action_required`.

## Việc cho Bin
- Máy chưa có ffmpeg: `winget install Gyan.FFmpeg` rồi mở terminal mới, chạy `ffmpeg -version`.
- Cài GitHub CLI để Antigravity tự mở PR: `winget install GitHub.cli` → `gh auth login`.
- Từ giờ **chờ tech lead review xong rồi mới merge** (PR #1 đã merge trước review).

## Kết luận
**Cần sửa** B1–B6 + N1–N5 trong branch `phase-0-fixes`. Sau khi tech lead duyệt PR sửa → bắt đầu Phase 1.
