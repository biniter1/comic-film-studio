# Comic Film Studio

Ứng dụng local (Windows) biến một chapter truyện tranh thành bộ **clip shot đã duyệt + thoại + phụ đề** để dựng trong CapCut.

**Quy trình:** Nhập chapter (URL/thư mục) → ghép dải & cắt khung → AI phân tích (Gemini) → Story Bible + shot list theo chuỗi
→ keyframe (Nano Banana, thủ công) → video (Muse, thủ công, nhiều tab song song) → duyệt take, nối khung → TTS → xuất gói CapCut.

## Tài liệu
- [`docs/SPEC.md`](docs/SPEC.md) — đặc tả kỹ thuật (nguồn sự thật)
- [`AGENTS.md`](AGENTS.md) — quy tắc cho AI coding agent
- [`docs/WORKFLOW.md`](docs/WORKFLOW.md) — cách phối hợp Bin ↔ Antigravity ↔ Claude
- [`docs/tasks/`](docs/tasks/) — nhiệm vụ từng phase
- [`docs/reviews/`](docs/reviews/) — nhận xét review

## Trạng thái
| Phase | Nội dung | Trạng thái |
|---|---|---|
| 0 | Khung dự án, job runner, SSE, CI | 🟡 sẵn sàng giao |
| 1 | Nhập chapter, ghép & cắt khung | ⏳ chờ Phase 0 |
| 2 | Phân tích AI, Story Bible, shot list | ⏳ |
| 3 | Hàng chờ thủ công, take, khung nối | ⏳ |
| 4 | Nhân vật, TTS, xuất CapCut | ⏳ |
| 5 | Hoàn thiện | ⏳ |

Hướng dẫn cài đặt sẽ có sau Phase 0.
