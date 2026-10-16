# Thí nghiệm: character sheet có giữ nhân vật nhất quán hơn không?

**Mục đích:** trước khi code Phase 2b, kiểm chứng bằng tay rằng lớp khóa 1 (§4.6 SPEC) đáng làm.
**Thời gian:** ~1 buổi. **Dùng:** Nano Banana (Gemini app), Muse. Chapter 400 (*Ta Là Tà Đế*).

## Chuẩn bị
1. Chọn **1 nhân vật chính** xuất hiện ở nhiều khung.
2. Lấy từ app (màn Khung → chuột phải ảnh khung → lưu):
   - **2–3 khung rõ mặt nhất** (cận/trung cảnh, càng ít che càng tốt) → dùng làm tham chiếu sheet.
   - **3 khung khác nhau để thử** (khác góc máy: 1 cận, 1 trung, 1 toàn) — có nhân vật này.

## Bước 1 — Tạo character sheet (Nano Banana)
Đính kèm 2–3 khung tham chiếu, dán prompt (sửa phần trong `{}`):

```
Create a professional character turnaround sheet of the SAME character shown in the attached comic panels.

Layout on a plain light-grey background, 16:9:
- top row: full body front view, 3/4 view, side view, back view (same scale, standing neutral pose, arms slightly away from body)
- bottom row: large face close-up front, face close-up 3/4, and 2 detail callouts of the outfit/accessories
Character: {young man, long black hair tied high, sharp red eyes, slim but athletic, black robe with gold trim}
Style: 2D anime cel-shaded, clean line art matching the source manhua, flat even lighting, no shadows on background.
Keep the face, hairstyle, eye colour, outfit and colours exactly as in the panels. Do not invent new accessories.
No text, no labels, no speech bubbles, no watermark.
```
Tạo 2–4 lần, **chọn 1 bản tốt nhất** (mặt giống truyện nhất, trang phục đủ chi tiết). Lưu `sheet.png`.

> Ghi lại: Nano Banana đính kèm tối đa được **bao nhiêu ảnh** một lượt? (Câu hỏi mở #6 trong SPEC.)

## Bước 2 — Tạo keyframe: KHÔNG có sheet (bộ A)
Với mỗi khung thử, đính kèm **chỉ ảnh khung** và dán:

```
Image 1 is a comic panel: keep its composition, poses and camera angle exactly.
Redraw it as a cinematic anime film frame: {2D anime cel-shaded, detailed background, cinematic lighting, depth of field}.
Remove all speech bubbles, text and sound-effect lettering; repaint the area behind them naturally.
16:9 frame. No text, no watermark.
```

## Bước 3 — Tạo keyframe: CÓ sheet (bộ B)
Cùng 3 khung, đính kèm **ảnh khung + sheet.png** (đúng thứ tự) và dán:

```
Image 1 is a comic panel: keep its composition, poses and camera angle exactly.
Image 2 is the character sheet of {Name}: the character in the panel is this person.
Redraw Image 1 as a cinematic anime film frame: {2D anime cel-shaded, detailed background, cinematic lighting, depth of field}.
{Name}: {young man, long black hair tied high, sharp red eyes, black robe with gold trim}.
Keep his face, hairstyle, eye colour and outfit exactly as in Image 2.
Remove all speech bubbles, text and sound-effect lettering; repaint the area behind them naturally.
16:9 frame. No text, no watermark.
```

## Bước 4 — Đưa qua Muse (cả A và B)
Mỗi keyframe làm 1 video 4–5s, cùng một khuôn prompt (chỉ sửa phần hành động):

```
Slow push in, medium close-up.
First, {he slowly raises his head}. Then, {his eyes narrow and his hair sways in the wind}. Finally, {he smirks}.
Ends on: {close-up of his face, smirking, looking straight at the camera}.
The young man in the black robe keeps the same face and outfit throughout. No new characters, no text, no cuts.
```

## Chấm điểm (điền vào bảng, 1–5)
| Tiêu chí | A1 | A2 | A3 | B1 | B2 | B3 |
|---|---|---|---|---|---|---|
| Keyframe: mặt giống truyện | | | | | | |
| Keyframe: tóc/mắt/trang phục đúng | | | | | | |
| 3 keyframe giống **nhau** (cùng một người) | — | — | — | — | — | — |
| Video: mặt giữ đến cuối clip | | | | | | |
| Video: làm đúng thứ tự First/Then/Finally | | | | | | |
| Video: chỉ 1 chuyển động máy, không cắt cảnh | | | | | | |

**Kết luận:** nếu bộ B hơn rõ ở hàng 1–4 → làm Phase 2b như SPEC. Nếu không khác → bỏ sheet, chỉ giữ `look_lock` dạng chữ (Phase 2b rút gọn). Hàng 5–6 dùng để chỉnh khuôn `video_prompt` cho Phase 2c.

Gửi lại cho tech lead: sheet.png, 6 keyframe, 6 video (hoặc ảnh chụp khung đầu/giữa/cuối) và bảng điểm.
