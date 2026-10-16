# Prototype tham chiếu (manga2anime / m2a)

Code thử nghiệm viết ngày 16/10/2026, **đã chạy thật** phần cắt khung, trích khung cuối và dò khoảnh khắc trong clip.
Phần gọi LLM (`llm.py`, `prompts.py`) mới test với provider giả.

**Chỉ để tham khảo/port** sang `backend/app/...` theo kiến trúc trong `docs/SPEC.md`. Không import trực tiếp.

| File | Dùng cho | Ghi chú |
|---|---|---|
| `panels.py` | Phase 1 — ghép dải, cắt khung (`split_image`, `stitch_vertical`), Phase 5 — AI gom mảnh (`_ai_groups`, `FRAME_SYSTEM`) | Đã test: ghép ảnh vắt 2 trang thành 1 khung |
| `media.py` | Phase 3 — `last_frame()` trích khung cuối, `probe()` | Thay `run()` bằng wrapper có timeout |
| `llm.py` | Phase 2 — client OpenAI-compatible, ép JSON, gửi lại lỗi validate cho model, cache theo hash | Gemini có endpoint OpenAI-compatible; có thể dùng `google-genai` thay thế |
| `prompts.py` | Phase 2 — 3 lượt READ / PLAN / SHOT | Cần sửa: Muse chỉ có ảnh đầu → thêm `start_state`/`end_state`, `transition_in`, `chain` |
| `rules.py` | Phase 2 — luật ép sau AI (tên chiêu → title, bổ sung thoại sót, chèn khóa style/nhân vật/chiêu) | Bỏ phần VFX/SFX hậu kỳ (CapCut làm) |
| `schemas.py` | Tham khảo field | Schema chính thức là SPEC §5 |
