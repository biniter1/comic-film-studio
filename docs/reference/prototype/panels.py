"""Tách panel từ trang truyện.

Hỗ trợ 2 kiểu:
- webtoon/manhua cuộn dọc: ghép tất cả trang thành 1 dải rồi cắt theo các dải nền (gutter) ngang.
- manga/comic dạng trang: cắt ngang trước, mỗi dải lại cắt dọc (đọc phải->trái nếu rtl).

Gutter = các hàng/cột gần như đồng màu (trắng hoặc đen). Không cần AI, chạy rất nhanh.
Panel quá mỏng (dải chữ như "Ma La Lục Thức Thông!") vẫn được giữ lại vì nó chứa chữ quan trọng;
đạo diễn sẽ phân loại nó là technique_name.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image

from .schemas import Panel

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def list_pages(pages_dir: Path) -> list[Path]:
    return sorted([p for p in pages_dir.iterdir() if p.suffix.lower() in IMG_EXT], key=natural_key)


def _gutter_mask(arr: np.ndarray, axis: int, std_thr: float, edge_thr: float) -> np.ndarray:
    """True nếu hàng (axis=1) / cột (axis=0) là gutter: gần như đồng màu."""
    std = arr.std(axis=axis)
    # độ biến thiên giữa các pixel liền kề: bắt được cả gutter có gradient nhẹ
    diff = np.abs(np.diff(arr, axis=axis)).mean(axis=axis)
    if diff.shape[0] != std.shape[0]:
        diff = np.pad(diff, (0, std.shape[0] - diff.shape[0]), mode="edge")
    return (std < std_thr) & (diff < edge_thr)


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Các đoạn liên tiếp mask=False (nội dung) dài >= min_len."""
    out, start = [], None
    for i, g in enumerate(mask):
        if not g and start is None:
            start = i
        elif g and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask)))
    return out


def _merge_close(runs: list[tuple[int, int]], gap: int) -> list[tuple[int, int]]:
    """Gộp các đoạn cách nhau quá ít (vết hở nhỏ bên trong 1 panel)."""
    if not runs:
        return runs
    out = [list(runs[0])]
    for a, b in runs[1:]:
        if a - out[-1][1] < gap:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [tuple(r) for r in out]


def split_image(img: Image.Image, *, min_h: int = 40, min_w: int = 80, std_thr: float = 6.0,
                edge_thr: float = 3.0, merge_gap: int = 6, columns: bool = False, rtl: bool = False):
    """Trả về list bbox (x, y, w, h)."""
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    H, W = gray.shape
    rows = _merge_close(_runs(_gutter_mask(gray, 1, std_thr, edge_thr), min_h), merge_gap)
    boxes = []
    for y0, y1 in rows:
        band = gray[y0:y1]
        cols = [(0, W)]
        if columns:
            c = _merge_close(_runs(_gutter_mask(band, 0, std_thr, edge_thr), min_w), merge_gap)
            cols = c or [(0, W)]
            if rtl:
                cols = cols[::-1]
        for x0, x1 in cols:
            # cắt viền đồng màu còn sót bên trong ô
            sub = gray[y0:y1, x0:x1]
            colmask = _gutter_mask(sub, 0, std_thr, edge_thr)
            nz = np.where(~colmask)[0]
            if len(nz):
                x0, x1 = x0 + int(nz[0]), x0 + int(nz[-1]) + 1
            boxes.append((x0, y0, x1 - x0, y1 - y0))
    return boxes


def stitch_vertical(pages: list[Path]) -> Image.Image:
    imgs = [Image.open(p).convert("RGB") for p in pages]
    w = max(i.width for i in imgs)
    imgs = [i if i.width == w else i.resize((w, round(i.height * w / i.width)), Image.LANCZOS) for i in imgs]
    out = Image.new("RGB", (w, sum(i.height for i in imgs)), "white")
    y = 0
    for i in imgs:
        out.paste(i, (0, y))
        y += i.height
    return out


FRAME_SYSTEM = """You segment a long vertical comic strip (a whole chapter stitched together) into FRAMES.
A FRAME = one complete picture that will become one film shot: the full artwork of one scene beat,
INCLUDING its parts that were split by page boundaries or thin dividers (e.g. the top and bottom halves of a
tower drawn across two pages), and including caption/technique-name text bands that belong to it.
You receive numbered FRAGMENTS (already cut at blank gutters), in reading order, as images; each label shows
its id and height. Rules:
- Group CONSECUTIVE fragments that form one picture/beat. Never reorder. Every fragment in exactly one group.
- A text band (title, technique name, caption) joins the art it introduces/labels.
- Separate different beats even if they touch (e.g. a face close-up then a wide shot of a building = 2 frames).
- If ONE fragment clearly contains several different pictures with no blank gap between them, give
  split_at = list of cut positions as fractions of that fragment's height (0-1), else [].
Return JSON {"groups":[{"fragments":["F001","F002"],"note":"short"}], "splits":{"F005":[0.48]}}"""


def _fragment_sheet(img: Image.Image, frags: list[tuple[str, tuple]], thumb_w: int = 320) -> list[Image.Image]:
    """Mỗi fragment -> thumbnail có nhãn id + chiều cao, giữ đúng tỉ lệ."""
    from PIL import ImageDraw
    out = []
    for fid, (x, y, w, h) in frags:
        t = img.crop((x, y, x + w, y + h))
        th = max(24, round(h * thumb_w / w))
        if th > 1400:
            th = 1400
        t = t.resize((thumb_w, th))
        d = ImageDraw.Draw(t)
        d.rectangle((0, 0, 150, 22), fill="red")
        d.text((5, 5), f"{fid}  h={h}", fill="white")
        out.append(t)
    return out


def _heuristic_groups(frags, min_frame_h: int):
    """Không có AI: gộp mảnh quá thấp (dải chữ, mẩu vụn) vào mảnh kế bên."""
    groups: list[list[str]] = []
    pending: list[str] = []
    for fid, (x, y, w, h) in frags:
        pending.append(fid)
        if h >= min_frame_h:
            groups.append(pending)
            pending = []
    if pending:
        if groups:
            groups[-1] += pending
        else:
            groups.append(pending)
    return groups, {}


def _ai_groups(img, frags, llm, window: int = 10):
    """Gửi từng cửa sổ fragment cho AI; nhóm cuối của mỗi cửa sổ được mang sang cửa sổ sau
    để không cắt nhầm khung nằm vắt qua ranh giới cửa sổ."""
    fmap = dict(frags)
    order = [f for f, _ in frags]
    groups: list[list[str]] = []
    splits: dict = {}
    i, carry = 0, []
    while i < len(order) or carry:
        ids = carry + order[i:i + window]
        i += window
        last = i >= len(order)
        thumbs = _fragment_sheet(img, [(f, fmap[f]) for f in ids])
        tmp_paths = []
        import tempfile
        for f, t in zip(ids, thumbs):
            fp = Path(tempfile.gettempdir()) / f"m2a_frag_{f}.jpg"
            t.save(fp, quality=85)
            tmp_paths.append(fp)

        def post(d, ids=ids):
            seen = [f for g in d["groups"] for f in g["fragments"]]
            if seen != ids:
                raise ValueError(f"groups phải phủ đúng và theo thứ tự {ids}, nhận {seen}")
            return d

        d = llm.json(FRAME_SYSTEM, f"Fragments in order: {ids}", tmp_paths, post=post)
        gs = [g["fragments"] for g in d["groups"]]
        splits.update({k: v for k, v in (d.get("splits") or {}).items() if k in ids})
        if last:
            groups += gs
            carry = []
            break
        groups += gs[:-1]
        carry = gs[-1]
    return groups, splits


def split_chapter(pages_dir: Path, out_dir: Path, *, mode: str = "webtoon", rtl: bool = False,
                  min_h: int = 40, max_h: int = 2400, min_frame_h: int = 160, llm=None) -> list[Panel]:
    """Ghép cả chapter thành 1 dải dài -> cắt thô theo gutter -> gom/cắt thành KHUNG hoàn chỉnh.

    mode: webtoon (cuộn dọc, ghép tất cả trang) | page (manga theo trang, cắt cả cột)
    llm : truyền LLM (Muse Spark) để AI gom mảnh; None = luật đơn giản.
    Kết quả: panels/P001.png... (mỗi file = 1 khung hoàn chỉnh) + fragments/ + stitched.jpg
    """
    pages = list_pages(pages_dir)
    if not pages:
        raise SystemExit(f"Không có ảnh trang nào trong {pages_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("P*.png"):
        old.unlink()

    if mode == "webtoon":
        sources = [("stitched", stitch_vertical(pages))]
        sources[0][1].save(out_dir.parent / "stitched.jpg", quality=90)
    else:
        sources = [(p.name, Image.open(p).convert("RGB")) for p in pages]

    panels: list[Panel] = []
    fcount = 0
    for name, img in sources:
        # 1) cắt thô theo gutter (không tốn token)
        frags = []
        for (x, y, w, h) in split_image(img, min_h=min_h, columns=(mode == "page"), rtl=rtl):
            for k in range(0, h, max_h):          # đoạn vẽ liền quá dài -> chia để AI xem được
                hh = min(max_h, h - k)
                if hh >= min_h or not frags:
                    fcount += 1
                    frags.append((f"F{fcount:03d}", (x, y + k, w, hh)))
                else:  # mẩu vụn cuối -> nhập vào mảnh trước
                    fid, (fx, fy, fw, fh) = frags[-1]
                    frags[-1] = (fid, (fx, fy, fw, fh + hh))
        # 2) gom thành khung
        groups, splits = (_ai_groups(img, frags, llm) if llm and mode == "webtoon"
                          else _heuristic_groups(frags, min_frame_h))
        fmap = dict(frags)
        # 3) cắt lại từ dải gốc full-res
        for g in groups:
            boxes = [fmap[f] for f in g]
            x0 = min(b[0] for b in boxes); x1 = max(b[0] + b[2] for b in boxes)
            y0 = min(b[1] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
            # cắt trong 1 fragment theo chỉ định của AI
            cuts = [y0]
            for f in g:
                fx, fy, fw, fh = fmap[f]
                cuts += [round(fy + fh * float(r)) for r in splits.get(f, []) if 0.05 < float(r) < 0.95]
            cuts = sorted(set(cuts)) + [y1]
            for a, b in zip(cuts, cuts[1:]):
                if b - a < min_h:
                    continue
                pid = f"P{len(panels) + 1:03d}"
                path = out_dir / f"{pid}.png"
                img.crop((x0, a, x1, b)).save(path)
                panels.append(Panel(id=pid, page=name, path=str(path), bbox=(x0, a, x1 - x0, b - a),
                                    width=x1 - x0, height=b - a))
    return panels


def contact_sheet(panels: list[Panel], out: Path, thumb_w: int = 360) -> Path:
    """Ảnh tổng hợp có đánh số panel - để kiểm tra nhanh kết quả cắt."""
    from PIL import ImageDraw
    thumbs = []
    for p in panels:
        im = Image.open(p.path)
        im = im.resize((thumb_w, max(1, round(im.height * thumb_w / im.width))))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 70, 26), fill="red")
        d.text((6, 6), p.id, fill="white")
        thumbs.append(im)
    cols = 4
    rows = [thumbs[i:i + cols] for i in range(0, len(thumbs), cols)]
    H = sum(max(t.height for t in r) + 10 for r in rows)
    sheet = Image.new("RGB", (cols * (thumb_w + 10), H), "#222")
    y = 0
    for r in rows:
        for j, t in enumerate(r):
            sheet.paste(t, (j * (thumb_w + 10), y))
        y += max(t.height for t in r) + 10
    sheet.save(out)
    return out
