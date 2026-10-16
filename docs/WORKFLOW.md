# Quy trình phối hợp: Bin ↔ Antigravity ↔ Claude

```
Claude (tech lead)            Bin (chủ dự án)                Antigravity (developer)
──────────────────            ───────────────                ───────────────────────
viết docs/tasks/phase-N.md
push lên main  ───────────►  bảo Antigravity:
                             "Đọc AGENTS.md rồi làm
                              docs/tasks/phase-N.md" ─────►  code trên branch phase-N-*
                                                             chạy test, mở PR
                             báo Claude: "review PR #x" ◄───
đọc code, chạy test,
comment trên PR + ghi
docs/reviews/phase-N.md ───► chuyển lời cho Antigravity:
                             "sửa theo review PR #x" ─────►  sửa, push thêm commit
                    (lặp đến khi Claude "approve")
                             merge PR
Claude viết phase-(N+1)
```

## Câu lệnh mẫu để đưa cho Antigravity
- Bắt đầu phase: **"Đọc AGENTS.md và docs/SPEC.md, sau đó thực hiện docs/tasks/phase-0.md. Làm trên branch mới, mở PR theo mẫu trong AGENTS.md."**
- Sau review: **"Đọc docs/reviews/phase-0.md (hoặc comment trên PR #1) và sửa toàn bộ mục 'Bắt buộc sửa'. Push vào cùng branch."**

## Câu lệnh mẫu để nói với Claude
- **"Review PR #1"** → Claude kéo branch, chạy test, đọc code, ghi nhận xét.
- **"Viết phase tiếp"** → sau khi PR được merge.

## Mức độ nhận xét trong review
- **Bắt buộc sửa**: sai SPEC, lỗi, thiếu test, rủi ro mất dữ liệu/bảo mật. Chưa sửa thì không merge.
- **Nên sửa**: chất lượng code, UX — sửa trong PR này nếu rẻ, không thì ghi lại.
- **Ghi chú**: để sau.
