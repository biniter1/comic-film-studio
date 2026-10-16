# Phase 1 — Project, nhập chapter, ghép & cắt khung

**Branch:** `phase-1-import` · **Điều kiện bắt đầu:** PR Phase 0 đã merge.
**Tham chiếu:** `docs/SPEC.md` §3.1, §5.4, §6, §7 (màn Dự án, Nhập chapter, Khung), §9, §10, §11
**Code tham khảo:** `docs/reference/prototype/panels.py` (thuật toán cắt khung)

> File này có thể được tech lead chỉnh lại sau khi review Phase 0.

## Mục tiêu
Người dùng tạo project → tạo chapter → nhập ảnh (URL hoặc thư mục) → sắp xếp trang → ghép dải → cắt khung tự động
→ **chỉnh gộp/tách khung bằng tay** → duyệt khung. Mọi thứ bền qua restart.

## Việc cần làm

### Backend
1. **Models + migration**: `Project`, `Chapter`, `SourcePage`, `Frame`, `Asset` (đủ trường SPEC §3.1/§5.4; trường của phase sau có thể để nullable).
2. **Project/Chapter API**: CRUD theo SPEC §9. Xóa project cần `?confirm=true`, chuyển thư mục vào `data_dir/trash/` thay vì xóa hẳn.
3. **Nhập thư mục** — `POST /chapters/{cid}/import/files` (multipart, nhiều file):
   - Lưu vào `tmp/`, kiểm tra bằng Pillow (`verify` + mở lại), từ chối file không phải ảnh, > 30MB, hoặc chiều rộng < 300px (báo lý do từng file).
   - Sắp xếp **natural sort** theo tên gốc; sha256 trùng → bỏ + cảnh báo.
   - Lưu thành `pages/001.jpg…` (giữ định dạng gốc nếu png/webp), tạo `Asset(kind=page)` + `SourcePage`.
   - Chạy qua job `import_local`, báo tiến độ.
4. **Nhập URL** — job `import_url` (`app/importer/`):
   - `validate_url()`: chỉ http/https; resolve DNS và **chặn IP private/loopback/link-local/multicast** (SSRF). Có unit test.
   - Lấy HTML bằng `httpx` (timeout 20s, follow redirect ≤ 5, kiểm tra lại IP sau redirect).
   - Nếu có `SiteProfile` khớp domain (`app/importer/profiles/*.yaml`: `domain`, `image_selector`, `image_attr` list ưu tiên, `referer`) → dùng; không có → chiến lược chung SPEC §6.1.
   - Tải ảnh song song tối đa 3, retry 3 lần (transient), header `Referer` = URL chapter, `User-Agent: ComicFilmStudio/0.1`.
   - 401/403/429 lặp lại hoặc trang không có ảnh nào → job `failed` với `error_category=permanent`, `message_vi` gợi ý dùng **Nhập thư mục**. **Không** thử vượt chặn.
   - Kết quả cũng đi qua bước kiểm tra/lưu như nhập thư mục.
   - Tạo sẵn 1 profile mẫu `profiles/_example.yaml` có chú thích.
5. **Trang** — `GET/PATCH /chapters/{cid}/pages`: đổi thứ tự (`[{id, idx}]`), đánh dấu `excluded`.
6. **Ghép & cắt** — job `stitch_and_cut` (`app/frames/`):
   - Port `stitch_vertical`, `split_image`, `_gutter_mask`, `_runs`, `_merge_close` từ prototype; bỏ phần AI (`_ai_groups`) — để Phase 5.
   - Mảnh < 160px gộp vào mảnh kế; đoạn liền > 2400px chia nhỏ.
   - Lưu `stitched.jpg` (nếu cao > 60.000px thì lưu thêm bản thu nhỏ `stitched_preview.jpg` rộng 400px cho UI).
   - Tạo `Frame` (`origin=auto`) + ảnh cắt `frames/F001.png…` từ **ảnh gốc full-res**.
7. **Chỉnh khung** — `PUT /chapters/{cid}/frames` nhận toàn bộ danh sách khoảng `[{y0, y1}]` (webtoon chỉ cắt ngang ở phase này; `x0/x1` = toàn chiều rộng):
   - Validate: tăng dần, không chồng lấn, nằm trong ảnh, mỗi khung ≥ 40px.
   - Cắt lại các ảnh khung **chỉ cho khoảng thay đổi**; khung mới `origin=manual`; giữ asset cũ (version) thay vì ghi đè.
   - `POST /chapters/{cid}/frames/approve` → `Chapter.status = frames_approved`. Sửa khung sau khi duyệt → trạng thái quay về `frames_draft` (Phase 2 sẽ dựa vào để cảnh báo phân tích cũ).
8. `GET /assets/{aid}/file` phục vụ file an toàn (qua `storage`).

### Frontend
1. **Dự án**: danh sách project (thẻ), tạo/đổi tên/xóa (hộp xác nhận), vào project → danh sách chapter + trạng thái.
2. **Nhập chapter**:
   - Tab "Từ URL": ô nhập + nút Tải; tiến độ job realtime; lỗi hiển thị `message_vi`.
   - Tab "Từ thư mục": vùng kéo-thả nhiều ảnh / chọn thư mục (`webkitdirectory`).
   - Lưới thumbnail trang: kéo-thả đổi thứ tự, bỏ chọn trang, badge cảnh báo (trùng, quá nhỏ).
   - Nút **"Ghép & cắt khung"** → chạy job, xong chuyển sang màn Khung.
3. **Khung** (màn hình quan trọng của phase này):
   - Cột trái: dải dọc thu nhỏ (cuộn được) với các **đường cắt** vẽ chồng lên.
   - Thao tác: **click vào khoảng hở giữa 2 khung → gộp**; **Alt+click trong 1 khung → thêm đường cắt tại đó**; **kéo đường cắt** để dời; Ctrl+Z hoàn tác (state cục bộ), nút **Lưu**.
   - Cột phải: danh sách khung (thumbnail + số thứ tự + chiều cao), click để cuộn tới.
   - Nút **"Duyệt khung"** (vô hiệu khi có thay đổi chưa lưu).
   - Hiệu năng: chapter dài 50.000–100.000px phải cuộn mượt (dùng ảnh preview thu nhỏ, tính tọa độ theo tỉ lệ).

## Test bắt buộc
- `test_frames_split.py`: tạo ảnh tổng hợp (Pillow) gồm 4 khối nội dung ngăn bởi gutter trắng/đen → cắt đúng 4 khung; dải chữ mỏng 60px bị gộp; ảnh vắt qua 2 trang được ghép liền thành 1 khung.
- `test_frames_edit.py`: PUT khoảng chồng lấn → 422; gộp/tách → số khung và file ảnh đúng; asset cũ vẫn còn.
- `test_importer_ssrf.py`: `http://127.0.0.1`, `http://10.0.0.1`, `http://169.254.169.254`, `file:///` bị chặn; domain resolve ra IP private bị chặn.
- `test_importer_parse.py`: HTML mẫu (fixture) với `data-src` + ảnh logo nhỏ → lấy đúng danh sách ảnh đúng thứ tự (mock HTTP bằng `respx`, **không** gọi mạng thật).
- `test_import_local.py`: natural sort `1.jpg, 2.jpg, 10.jpg`; file hỏng bị từ chối có lý do; trùng sha256 bị bỏ.
- E2E Playwright (1 kịch bản): tạo project → chapter → upload 3 ảnh fixture → ghép & cắt → gộp 2 khung → lưu → duyệt.

## Tiêu chí nghiệm thu
- [ ] Nhập 1 chapter thật từ thư mục (~40–80 ảnh) trên Windows, thời gian ghép+cắt < 60s.
- [ ] Nhập URL: chạy được với ít nhất 1 web mẫu Bin cung cấp **hoặc** báo lỗi rõ ràng + gợi ý nhập thư mục.
- [ ] Màn Khung: gộp/tách/dời đường cắt hoạt động, lưu xong reload trang vẫn giữ.
- [ ] Tắt app giữa lúc đang nhập → mở lại: job tiếp tục hoặc báo lỗi rõ, không có trang “ma” nửa vời.
- [ ] Mọi test pass, CI xanh; ảnh chụp màn hình màn Nhập và Khung trong PR.

## Ngoài phạm vi
Phân tích AI, Story Bible, shot, AI gom khung, Playwright cho trang JS (ghi vào "Đề xuất" nếu web mẫu cần).
