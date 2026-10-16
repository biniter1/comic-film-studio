# Phase 0 — Khung dự án (scaffold)

**Branch:** `phase-0-scaffold` · **Tham chiếu:** `docs/SPEC.md` §2, §5.6, §9 (jobs, events, settings), §10, §11, §12

## Mục tiêu
Có một ứng dụng **chạy được trên Windows** gồm backend FastAPI + frontend React, DB SQLite có migration,
job runner bền qua restart, SSE đẩy trạng thái job lên UI, và CI. Chưa có tính năng nghiệp vụ.

## Việc cần làm

### 1. Cấu trúc repo
```
backend/
  pyproject.toml            # uv; script entry: cfs = "app.main:run"
  app/
    main.py                 # tạo FastAPI app, mount /api, phục vụ frontend/dist ở "/", hàm run() chạy uvicorn 127.0.0.1:8765
    config.py               # Settings (pydantic-settings): data_dir, host, port, max_parallel_muse_tabs...; đọc secrets.env
    db.py                   # engine SQLite (WAL, foreign_keys=ON), session dependency
    storage.py              # resolve path an toàn trong data_dir, tạo thư mục project/chapter
    logging.py              # log JSON-lines ra data_dir/logs + console; bộ lọc che secret
    errors.py               # AppError(code, message_vi, details) + exception handler -> format lỗi SPEC §9
    models/                 # SQLModel tables
      job.py
    schemas/
      job.py
    jobs/
      runner.py             # worker async
      registry.py           # @job_handler("type") đăng ký handler
      handlers/demo.py      # job "demo_sleep" để kiểm thử
    api/
      health.py             # GET /api/health
      jobs.py               # GET /api/jobs, POST /api/jobs/{id}/retry|cancel, POST /api/jobs/demo
      events.py             # GET /api/events (SSE)
      settings.py           # GET/PUT /api/settings, GET /api/settings/providers/status
  migrations/               # alembic
  tests/
frontend/
  package.json, vite.config.ts (proxy /api -> 127.0.0.1:8765), tsconfig strict
  src/
    main.tsx, App.tsx       # React Router
    api/client.ts           # fetch wrapper + kiểu lỗi chuẩn
    api/events.ts           # hook useEvents() dùng EventSource, cập nhật cache TanStack Query
    layout/AppShell.tsx     # sidebar + main + status bar
    pages/                  # các trang placeholder (xem mục 4)
scripts/
  dev.py                    # chạy backend + `npm run dev` song song (Windows-friendly)
.github/workflows/ci.yml
.gitignore                  # data/, .env, secrets.env, node_modules, dist, __pycache__, *.db
README.md                   # cách cài & chạy trên Windows
```

### 2. Job runner (quan trọng — các phase sau dựa vào đây)
- Bảng `jobs` đúng schema SPEC §5.6 (`depends_on` lưu JSON list).
- `JobService.enqueue(type, payload, depends_on=[], input_hash=None) -> Job`:
  - nếu `input_hash` trùng 1 job `succeeded` cùng `type` → trả job đó (idempotent), không tạo mới.
- Worker: vòng lặp async, lấy job `queued` có mọi `depends_on` đã `succeeded`, chạy tối đa `settings.job_concurrency` (mặc định 2) cùng lúc.
- Handler nhận `JobContext` có: `payload`, `report_progress(0..1, message)`, `log(msg)`, `is_cancelled()`.
- Lỗi: handler raise `JobError(category, message, user_action_required=None)`; `transient` → retry backoff (2s, 8s, 30s) tới `max_attempts`; loại khác → `failed`.
- Khởi động app: job `running` → `queued` (attempts giữ nguyên).
- Hủy: đặt cờ; handler tự kiểm tra `is_cancelled()`; job `queued` hủy ngay.
- Mỗi thay đổi trạng thái → phát sự kiện `job.updated` qua bus nội bộ → SSE.
- Log mỗi job: `data_dir/jobs/<job_id>.log`.

### 3. SSE
- `GET /api/events?chapter_id=` (chapter_id tùy chọn, Phase 0 bỏ qua lọc). Sự kiện: `event: job.updated`, `data: <Job JSON>`.
- Heartbeat comment mỗi 15s. Frontend tự kết nối lại.

### 4. Frontend shell
- Layout tối theo SPEC §7: sidebar với các mục **Dự án, Nhập chapter, Khung, Kịch bản, Bảng shot, Hàng chờ, Thoại, Xuất, Job, Cài đặt** (trang chưa làm hiển thị "Sẽ có ở phase sau").
- Trang **Job** hoạt động thật: bảng job, lọc trạng thái, nút Retry/Hủy, cập nhật realtime qua SSE; nút "Tạo job thử" gọi `POST /api/jobs/demo` (job ngủ 5s, báo tiến độ mỗi giây).
- Trang **Cài đặt**: hiện `data_dir`, trạng thái provider (`gemini: chưa cấu hình / đã cấu hình`) — **không** hiện giá trị key.
- Thanh trạng thái dưới: số job đang chạy / lỗi.

### 5. CI (`.github/workflows/ci.yml`, ubuntu-latest)
- Backend: `uv sync`, `uv run ruff check`, `uv run ruff format --check`, `uv run pytest`.
- Frontend: `npm ci`, `npm run lint`, `npm run build`.

## Test bắt buộc (`backend/tests/`)
- `test_jobs_runner.py`: chạy job demo tới `succeeded`; job có `depends_on` chỉ chạy sau job cha; job lỗi `transient` được retry đúng số lần; idempotent theo `input_hash`; **mô phỏng restart** (job `running` trong DB → `queued` sau khi khởi tạo runner mới) .
- `test_storage.py`: path traversal (`../`, đường dẫn tuyệt đối, ổ đĩa `C:\`) bị chặn.
- `test_errors.py`: lỗi trả đúng format `{"error": {"code","message_vi","details"}}`.
- `test_logging.py`: chuỗi giống API key bị che trong log.

## Tiêu chí nghiệm thu
- [ ] Trên Windows: `cd backend && uv run cfs` mở được `http://127.0.0.1:8765` (sau khi `npm run build`).
- [ ] `python scripts/dev.py` chạy chế độ dev (hot reload cả 2 phía).
- [ ] Tạo job thử → thấy tiến độ chạy realtime trên trang Job mà không cần F5.
- [ ] Tắt app khi job đang chạy → mở lại → job tiếp tục và kết thúc `succeeded`.
- [ ] Không có API key nào trong repo; `secrets.env` nằm trong `data_dir`.
- [ ] CI xanh. Mọi test ở trên pass (dán output).
- [ ] README có hướng dẫn cài trên Windows (uv, Node LTS, ffmpeg vào PATH) + kiểm tra `ffmpeg -version` khi khởi động (thiếu thì cảnh báo trên trang Cài đặt, không crash).

## Ngoài phạm vi
Project/chapter, nhập ảnh, AI, mọi màn hình nghiệp vụ.
