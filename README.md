# Comic Film Studio

Ứng dụng local (Windows 11) biến một chapter truyện tranh thành bộ **clip shot đã duyệt + thoại + phụ đề** để dựng trong CapCut.

**Quy trình:** Nhập chapter (URL/thư mục) → ghép dải & cắt khung → AI phân tích (Gemini) → Story Bible + shot list theo chuỗi → keyframe (Nano Banana, thủ công) → video (Muse, thủ công, nhiều tab song song) → duyệt take, nối khung → TTS → xuất gói CapCut.

---

## 1. Yêu cầu hệ thống trên Windows 11

Trước khi cài đặt, hãy đảm bảo máy tính đã cài đặt các công cụ sau:

1. **Python 3.12 & uv**:
   - Cài đặt `uv` (công cụ quản lý Python cực nhanh):
     ```powershell
     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     ```
     hoặc:
     ```powershell
     python -m pip install uv
     ```
   - `uv` sẽ tự động tải và quản lý Python 3.12 trong môi trường người dùng mà không cần quyền Admin:
     ```powershell
     uv python install 3.12
     ```

2. **Node.js (LTS 20+) & npm**:
   - Tải bộ cài đặt từ [Node.js Official](https://nodejs.org/) hoặc qua winget:
     ```powershell
     winget install OpenJS.NodeJS.LTS
     ```

3. **FFmpeg**:
   - Dùng để trích xuất khung hình cuối (`extract_last_frame`) và kiểm tra thông số media.
   - Cài đặt qua winget:
     ```powershell
     winget install Gyan.FFmpeg
     ```
     hoặc tải từ [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) và thêm thư mục `bin` vào biến môi trường `PATH`.
   - *Lưu ý:* Comic Film Studio tự động kiểm tra `ffmpeg -version` khi khởi động. Nếu chưa cài đặt, hệ thống sẽ hiển thị cảnh báo trên trang **Cài đặt** và tiếp tục hoạt động mà không bị crash.

4. **Git**:
   - Cài đặt qua [git-scm.com](https://git-scm.com/) hoặc `winget install Git.Git`.

---

## 2. Hướng dẫn cài đặt & chạy

### Bước 1: Clone repo
```powershell
git clone https://github.com/biniter1/comic-film-studio.git
cd comic-film-studio
```

### Bước 2: Cài đặt phụ thuộc & Build giao diện
```powershell
# Cài đặt backend (tự động tạo venv Python 3.12)
cd backend
uv sync
uv run alembic upgrade head
cd ..

# Cài đặt và build frontend
cd frontend
npm install
npm run build
cd ..
```

### Bước 3: Khởi chạy ứng dụng

- **Chế độ chạy chuẩn (Production mode):**
  ```powershell
  cd backend
  uv run cfs
  ```
  Mở trình duyệt truy cập: **`http://127.0.0.1:8765`**

- **Chế độ phát triển (Development mode - hot reload cả 2 phía):**
  ```powershell
  python scripts/dev.py
  ```
  Giao diện frontend tự động mở tại `http://localhost:5173` và proxy API về backend tại `http://127.0.0.1:8765`.

---

## 3. Kiểm thử & Kiểm tra mã nguồn

Tất cả các kiểm tra phải vượt qua trước khi mở Pull Request:

```powershell
# Kiểm tra backend
cd backend
uv run ruff check
uv run ruff format --check
uv run pytest

# Kiểm tra frontend
cd ../frontend
npm run lint
npm run build
```

---

## 4. Tài liệu kỹ thuật
- [`docs/SPEC.md`](docs/SPEC.md) — Đặc tả kỹ thuật chi tiết (nguồn sự thật)
- [`AGENTS.md`](AGENTS.md) — Quy tắc làm việc cho AI coding agent
- [`docs/WORKFLOW.md`](docs/WORKFLOW.md) — Quy trình phối hợp Bin ↔ Antigravity ↔ Claude
- [`docs/tasks/`](docs/tasks/) — Danh sách nhiệm vụ từng phase

---

## 5. Trạng thái dự án
| Phase | Nội dung | Trạng thái |
|---|---|---|
| **0** | Khung dự án, backend FastAPI, frontend React, DB migration, job runner, SSE, CI | 🟢 Hoàn thành |
| **1** | Nhập chapter, ghép dải & cắt khung | ⏳ Sẵn sàng |
| **2** | Phân tích AI, Story Bible, shot list | ⏳ |
| **3** | Hàng chờ thủ công, take, khung nối | ⏳ |
| **4** | Nhân vật, TTS, xuất CapCut | ⏳ |
| **5** | Hoàn thiện & đánh bóng | ⏳ |

## Kiểm thử end-to-end (Phase 1+)
```powershell
cd frontend
npx playwright install chromium   # lần đầu
npm run e2e                       # build frontend + chạy backend thật trên thư mục dữ liệu tạm + Playwright
```
Ảnh chụp màn hình lưu ở `frontend/e2e/screenshots/`.
