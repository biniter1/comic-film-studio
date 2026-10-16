# AGENTS.md — Hướng dẫn cho AI coding agent (Antigravity)

Bạn là **developer** của dự án Comic Film Studio. Tech lead là Claude (review qua Pull Request).
Chủ dự án là Bin (người duyệt cuối, merge PR).

## Nguồn sự thật
1. `docs/SPEC.md` — kiến trúc, schema, API, trạng thái. **Luôn đọc trước khi code.**
2. `docs/tasks/phase-N.md` — nhiệm vụ của phase hiện tại. Chỉ làm đúng phạm vi trong file đó.
3. `docs/reviews/` — nhận xét của tech lead cho các PR trước. Đọc nhận xét mới nhất trước khi bắt đầu.
4. `docs/reference/prototype/` — code thử nghiệm đã chạy được (thuật toán cắt khung, trích khung cuối, gọi LLM có retry, luật shot). **Chỉ để tham khảo/port**, không import trực tiếp.

## Quy tắc làm việc
- **Mỗi phase = 1 branch + 1 PR**: branch `phase-N-<slug>` (vd `phase-1-import`), PR vào `main`. Không push thẳng `main`.
- Commit nhỏ, thông điệp tiếng Anh dạng `feat(importer): ...`, `fix(frames): ...`, `test: ...`, `docs: ...`.
- Không tự ý đổi hợp đồng dữ liệu (schema, API route, enum trạng thái). Nếu **bắt buộc** phải đổi: sửa `docs/SPEC.md` trong cùng PR và ghi rõ ở mục "Thay đổi SPEC" của mô tả PR.
- Không tự thêm tính năng ngoài phạm vi phase. Ý tưởng hay → ghi vào mục "Đề xuất" của PR.
- Gặp chỗ SPEC không rõ: **không bịa**. Chọn phương án đơn giản nhất, ghi vào mục "Câu hỏi cho tech lead" trong PR.
- Không báo "đã xong/đã pass" nếu chưa thực sự chạy. Dán output lệnh test thật vào PR.

## Kỹ thuật
- Windows 11 là môi trường chính: dùng `pathlib`, không hard-code `/`, không dùng lệnh chỉ có trên Linux trong code chạy thật. Script tiện ích viết bằng Python (hoặc cung cấp cả `.ps1`).
- Python 3.12, quản lý bằng `uv`. Lint/format: `ruff check` + `ruff format`. Type hints đầy đủ.
- Frontend: React 18 + TypeScript strict + Vite + TanStack Query + Tailwind + shadcn/ui. `npm run lint`, `npm run build` phải pass.
- Gọi ffmpeg/ffprobe bằng `subprocess.run([...], timeout=...)`, **không** `shell=True`.
- Đường dẫn file trong DB là **tương đối** so với thư mục project. Mọi truy cập file phải đi qua module `storage` có kiểm tra nằm trong `data_dir`.
- Không ghi API key vào code, log, file trong repo. Đọc từ `secrets.env` trong `data_dir` hoặc biến môi trường.
- Giao diện: chữ hiển thị **tiếng Việt**; tên biến, API, log kỹ thuật **tiếng Anh**.
- Test không được gọi API AI thật; dùng provider giả.

## Mẫu mô tả PR (bắt buộc)
```
## Phase N — <tên>
### Đã làm
- ...
### Cách chạy / kiểm tra
uv run ...   npm run ...
### Kết quả test (dán output thật)
...
### Ảnh chụp màn hình UI
...
### Thay đổi SPEC
- (không có) / ...
### Câu hỏi cho tech lead
- ...
### Đề xuất
- ...
### Checklist tiêu chí nghiệm thu (copy từ docs/tasks/phase-N.md, đánh dấu)
- [ ] ...
```
