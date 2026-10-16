# Phase 2a — Đọc truyện, bóc thoại, biên tập thoại & thư viện thuật ngữ

**Branch:** `phase-2a-dialogue` · **Điều kiện bắt đầu:** PR Phase 1 đã merge.
**Tham chiếu:** `docs/SPEC.md` §4.1, §4.2, **§4.5**, §5.1, §5.1b, §5.1c, §5.2, §5.6, §9
**Code tham khảo:** `docs/reference/prototype/llm.py` (ép JSON + gửi lại lỗi validate + cache), `prompts.py` (READ_SYSTEM)

## Mục tiêu
Từ một chapter đã **duyệt khung**, AI:
1. Phân loại từng khung (`scene / dialogue_only / caption / sfx_only / credit`).
2. Bóc **mọi câu chữ** theo thứ tự đọc, đoán **người nói** (nhân vật nào, nam/nữ, tuổi) kèm độ tin cậy, và **gắn câu vào khung cảnh** (khung chỉ có thoại → gắn vào cảnh trước/sau).
3. **Biên tập lại toàn bộ thoại** của chapter cho hay, đúng nghĩa, nhất quán **thuật ngữ** và **xưng hô**.

Người dùng soát và sửa trên màn **Kịch bản thoại** và **Thuật ngữ**, rồi **duyệt kịch bản thoại** (cổng duyệt trước Phase 2b).

## Việc cần làm

### 1. Provider adapter (`backend/app/providers/`)
- `base.py`: interface `AnalysisProvider.generate_json(stage, system_prompt, user_text, images: list[Path], schema: type[BaseModel]) -> BaseModel` + `ProviderError(category, message_vi)` với `category` ∈ `transient | quota | invalid_output | permanent`.
- `gemini.py` (SDK `google-genai`, thêm vào dependency):
  - Model cấu hình trong Settings: `analysis_model_vision` (mặc định `gemini-2.5-flash`), `analysis_model_text` (mặc định `gemini-2.5-pro`). **Không** hard-code ở nơi khác.
  - Dùng structured output (`response_mime_type="application/json"` + `response_schema`) nếu SDK hỗ trợ; vẫn validate lại bằng Pydantic.
  - Ảnh: thu nhỏ cạnh dài ≤ 1600px, JPEG q=85 trước khi gửi.
  - HTTP 429 / `RESOURCE_EXHAUSTED`: phân biệt **rate limit** (`transient`, backoff) và **hết hạn mức ngày** (`quota` → job `failed` + `user_action_required="Hết hạn mức Gemini. Dùng chế độ thủ công hoặc chờ ngày mai."`).
  - Key đọc từ `settings.gemini_api_key` (đã có từ Phase 0). Thiếu key → `permanent` + hướng dẫn vào Cài đặt.
- `manual.py`: chế độ thủ công (SPEC §4.2) — tạo **gói** (zip: ảnh + `prompt.txt` có sẵn schema và ngữ cảnh) và nhận **JSON dán vào**, validate y hệt API.
- `fake.py`: provider giả đọc JSON fixture theo `stage` — dùng cho **mọi test** (không gọi API thật trong test/CI).
- Validate lỗi → gửi lại lỗi cho model tối đa 3 lần; vẫn lỗi → lưu `raw_output` vào `analysis/raw/…` và `AnalysisRun.status=failed`.
- Cache theo `input_hash = sha256(stage, model, prompt_version, inputs)` — chạy lại không tốn quota.

### 2. Prompt (`backend/app/providers/prompts/`)
- `read.v1.md`, `dialogue.v1.md` — tiếng Anh cho chỉ dẫn, yêu cầu **giữ nguyên tiếng Việt** của chữ trong truyện.
- `read`: ngoài các trường SPEC §5.1, bắt buộc: `frame_type`, mỗi câu có `line_no`, người nói + giới tính + tuổi + `speaker_confidence`, `belongs_to`. Gửi kèm **1 khung trước và 1 khung sau** lô (đánh dấu "chỉ để ngữ cảnh, không trả kết quả cho khung này"), danh sách nhân vật đã biết (`key`, tên, `aliases`, giới tính) và thuật ngữ đã duyệt.
  - Nhắc model: đuôi bong bóng chỉ về ai → người nói; bong bóng răng cưa = hét; bong bóng mây = suy nghĩ; khung chữ vuông = dẫn truyện; banner nhóm dịch/link web = `credit`.
- `dialogue`: chỉ chữ, **toàn bộ chapter một lượt** (chapter quá dài → chia đoạn ~150 câu, có 10 câu chồng lấn và gửi kèm bảng thuật ngữ/xưng hô hiện tại). Quy tắc biên tập theo SPEC §4.5.

### 3. Dữ liệu (migration Alembic mới)
- `frames`: thêm `frame_type` (nullable), `frame_type_source` (`ai | user`).
- Bảng `characters` (project-level): `key`, `name`, `aliases` (JSON), `gender`, `age_group`, `voice_style`, `look_lock` (nullable ở 2a), `voice_id` (nullable), `status` (`suggested | approved`).
- Bảng `dialogue_lines` (SPEC §5.1b), `glossary_terms`, `address_rules` (SPEC §5.1c), `analysis_runs` (SPEC §3.1).
- `Chapter.status` thêm: `analyzing`, `dialogue_draft`, `dialogue_approved`.

### 4. Job & luật
- Job `analysis_read` (`def`): theo lô 6 khung có ngữ cảnh; tạo `FrameReading`, cập nhật `frame_type` (không ghi đè nếu `frame_type_source=user`), tạo `DialogueLine` (`text = text_raw`, `edited_by = none`), đề xuất nhân vật mới (`status=suggested`). Tiến độ theo lô.
  - Quy `belongs_to` → `anchor_frame_id`: `self` nếu khung là `scene`; `prev/next` → khung `scene` gần nhất theo hướng đó; không có → khung `scene` gần nhất bất kỳ.
  - Khung `credit` → đề xuất bỏ (hiện trên UI, **không tự xóa**).
- Job `analysis_dialogue` (`def`, `depends_on` read): biên tập; **luật code §4.5** (thay biến thể → thuật ngữ chuẩn, đủ 1-1 câu, cờ `needs_review`); thêm đề xuất thuật ngữ/xưng hô (`suggested`). Không ghi đè câu `edited_by=user`.
- Chạy lại `read` khi khung đã đổi (chapter không còn `frames_approved` nguyên trạng) → cảnh báo, xóa `dialogue_lines` cũ của chapter (giữ bản sao `analysis/history/`).

### 5. API (thêm vào SPEC §9 trong PR)
- `POST /chapters/{cid}/analysis/{stage}` body `{mode: "api" | "manual"}` → job (api) hoặc thông tin gói (manual)
- `GET /chapters/{cid}/analysis/{stage}/bundle` · `POST /chapters/{cid}/analysis/{stage}/paste`
- `GET /chapters/{cid}/dialogue` · `PATCH /dialogue/{lid}` (text, speaker, kind, anchor_frame_id) · `POST /dialogue/{lid}/revert` (về `text_raw`) · `POST /chapters/{cid}/dialogue/approve`
- `PATCH /frames/{fid}` (`frame_type`)
- `GET/POST/PATCH/DELETE /projects/{pid}/glossary` · `…/address-rules` · `…/characters`
- Gộp thuật ngữ: `POST /projects/{pid}/glossary/{id}/merge` `{into_id}` → variants gộp lại.

### 6. Frontend
- Màn **Kịch bản thoại** (`/chapters/:cid/dialogue`):
  - Nút "Phân tích bằng Gemini" / "Chế độ thủ công" + tiến độ job.
  - Bảng câu theo thứ tự đọc: ảnh khung nguồn (thu nhỏ), **người nói** (dropdown nhân vật + "nhân vật phụ"; tô vàng nếu `speaker_confidence < 0.7`), loại, **Bản gốc | Bản biên tập** (hiện khác biệt, sửa tại chỗ), gắn vào khung cảnh nào (đổi được), nút "Về bản gốc".
  - Bộ lọc: chỉ câu cần soát · theo nhân vật · theo khung.
  - Cột trái: danh sách khung với loại khung (đổi được); khung `credit` có nút "Bỏ khung" (gọi lại API khung của Phase 1).
  - Nút **Duyệt kịch bản thoại** (khóa khi còn câu `needs_review` chưa xem — có "Đánh dấu đã xem tất cả").
- Màn **Thuật ngữ** (`/projects/:pid/glossary`): 3 tab **Thuật ngữ / Xưng hô / Nhân vật** — duyệt/bỏ đề xuất, sửa, gộp biến thể, thêm tay; nhân vật: tên, bí danh, giới tính, tuổi, kiểu giọng.
- Sidebar: mục "Kịch bản" trỏ tới màn Kịch bản thoại của chapter gần nhất.

## Test bắt buộc (không gọi API thật)
- `test_providers_fake.py`: provider giả + validate lỗi → gửi lại → thành công lần 2; lỗi 3 lần → `failed` + raw output được lưu.
- `test_gemini_errors.py`: mock SDK — rate limit → `transient`; hết hạn mức → `quota` + `user_action_required`; thiếu key → `permanent`.
- `test_anchor.py`: `dialogue_only` giữa 2 `scene` với `belongs_to=prev/next` → anchor đúng; đầu/cuối chapter; nhiều `dialogue_only` liên tiếp.
- `test_dialogue_rules.py`: biến thể → thuật ngữ chuẩn (ranh giới từ, hoa/thường, không thay trong từ khác); thiếu/thừa câu → lỗi `invalid_output`; lệch độ dài > 40% → `needs_review`; câu `edited_by=user` không bị ghi đè khi chạy lại.
- `test_manual_mode.py`: tạo gói (zip có ảnh + prompt) → dán JSON sai → 422 chỉ rõ trường → dán đúng → dữ liệu như chế độ API.
- E2E: chapter 3 khung (1 `dialogue_only` ở giữa) với provider giả → màn Kịch bản thoại hiện câu gắn vào khung trước, sửa 1 câu, đổi người nói, duyệt.

## Tiêu chí nghiệm thu
- [ ] Chạy thật với **chapter 400** (khung đã duyệt) bằng Gemini key của Bin: khung chỉ có thoại (vd #40) không bị coi là cảnh; câu của nó gắn đúng khung trước/sau.
- [ ] Người nói đúng ở phần lớn câu; câu không chắc được tô vàng.
- [ ] Bản biên tập đọc tự nhiên, không đổi tình tiết; thuật ngữ & xưng hô nhất quán trong cả chapter.
- [ ] Hết hạn mức Gemini → báo rõ, chế độ thủ công làm được trọn quy trình.
- [ ] Sửa tay một câu rồi chạy lại `dialogue` → câu sửa tay giữ nguyên.
- [ ] Mọi test pass, CI xanh, ảnh chụp màn Kịch bản thoại & Thuật ngữ trong PR.

## Ngoài phạm vi
Lượt `plan`/`shots`, shot phản ứng, TTS, keyframe/video (Phase 2b trở đi).
