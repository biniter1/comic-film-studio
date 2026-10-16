"""Virtual stitched strip + automatic frame detection (SPEC §6.3).

The chapter is never written as one giant image (JPEG is limited to 65 535 px and a
100 000 px PNG is slow). Instead pages are *virtually* stacked: each page is scaled to a
common width ``W`` and placed at ``y_offset`` on the strip. Frames are ranges ``[y0, y1)``
on that strip and are cropped by compositing the overlapping pages.

Gutter detection is row-wise, so it is computed page by page (low memory) and the row masks
are concatenated — which is exactly why a panel split across two pages is reassembled.
Algorithm ported from ``docs/reference/prototype/panels.py``.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

STD_THR = 6.0  # a gutter row is nearly uniform...
EDGE_THR = 3.0  # ...and has almost no change between neighbouring pixels
MIN_CONTENT_H = 40  # content runs shorter than this are treated as noise
MERGE_GAP = 6  # tiny gaps inside a panel are not gutters
MIN_FRAME_H = 160  # thinner pieces (text bands, crumbs) merge into the next frame
MAX_FRAME_H = 2400  # continuous art taller than this is split for downstream models


@dataclass
class StripPage:
    page_id: str
    path: Path
    width: int
    height: int
    scaled_h: int
    y0: int  # offset on the strip

    @property
    def y1(self) -> int:
        return self.y0 + self.scaled_h


@dataclass
class Strip:
    width: int
    pages: list[StripPage]

    @property
    def height(self) -> int:
        return self.pages[-1].y1 if self.pages else 0


def build_strip(pages: list[tuple[str, Path, int, int]]) -> Strip:
    """pages: (page_id, absolute_path, width, height) in reading order."""
    if not pages:
        return Strip(0, [])
    width = max(w for _, _, w, _ in pages)
    out: list[StripPage] = []
    y = 0
    for pid, path, w, h in pages:
        sh = h if w == width else max(1, round(h * width / w))
        out.append(StripPage(pid, path, w, h, sh, y))
        y += sh
    return Strip(width, out)


def load_scaled(page: StripPage, width: int, mode: str = "RGB") -> Image.Image:
    with Image.open(page.path) as im:
        im = im.convert(mode)
        if im.width != width:
            im = im.resize((width, page.scaled_h), Image.LANCZOS)
        return im.copy()


def gutter_rows(gray: np.ndarray) -> np.ndarray:
    """True for rows that look like a gutter (uniform colour, white or black)."""
    g = gray.astype(np.float32)
    std = g.std(axis=1)
    diff = np.abs(np.diff(g, axis=1)).mean(axis=1) if g.shape[1] > 1 else np.zeros(g.shape[0])
    return (std < STD_THR) & (diff < EDGE_THR)


def _content_runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Runs where mask is False (content) with length >= min_len."""
    padded = np.concatenate([[True], mask, [True]])
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    starts, ends = changes[0::2], changes[1::2]
    return [(int(a), int(b)) for a, b in zip(starts, ends) if b - a >= min_len]


def _merge_close(runs: list[tuple[int, int]], gap: int) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for a, b in runs:
        if out and a - out[-1][1] < gap:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _split_long(runs: list[tuple[int, int]], max_h: int) -> list[tuple[int, int]]:
    out = []
    for a, b in runs:
        n = max(1, -(-(b - a) // max_h))  # ceil
        step = (b - a) / n
        for i in range(n):
            out.append((a + round(i * step), a + round((i + 1) * step)))
    return out


def _merge_thin(runs: list[tuple[int, int]], min_frame_h: int) -> list[tuple[int, int]]:
    """Thin pieces (text bands) join the NEXT frame; a thin tail joins the previous one."""
    out: list[tuple[int, int]] = []
    pending: tuple[int, int] | None = None
    for a, b in runs:
        if pending:
            a = pending[0]
            pending = None
        if b - a < min_frame_h:
            pending = (a, b)
        else:
            out.append((a, b))
    if pending:
        if out:
            out[-1] = (out[-1][0], pending[1])
        else:
            out.append(pending)
    return out


def strip_gutter_mask(strip: Strip) -> np.ndarray:
    masks = []
    for p in strip.pages:
        gray = np.asarray(load_scaled(p, strip.width, "L"))
        masks.append(gutter_rows(gray))
    return np.concatenate(masks) if masks else np.zeros(0, dtype=bool)


def detect_frames(
    strip: Strip,
    *,
    min_content_h: int = MIN_CONTENT_H,
    merge_gap: int = MERGE_GAP,
    min_frame_h: int = MIN_FRAME_H,
    max_frame_h: int = MAX_FRAME_H,
    mask: np.ndarray | None = None,
) -> list[tuple[int, int]]:
    mask = strip_gutter_mask(strip) if mask is None else mask
    runs = _merge_close(_content_runs(mask, min_content_h), merge_gap)
    runs = _split_long(runs, max_frame_h)
    return _merge_thin(runs, min_frame_h)


def crop_frame(strip: Strip, y0: int, y1: int) -> Image.Image:
    """Composite the strip range [y0, y1) from the overlapping pages (full width)."""
    out = Image.new("RGB", (strip.width, y1 - y0), "white")
    for p in strip.pages:
        top, bottom = max(y0, p.y0), min(y1, p.y1)
        if top >= bottom:
            continue
        im = load_scaled(p, strip.width)
        out.paste(im.crop((0, top - p.y0, strip.width, bottom - p.y0)), (0, top - y0))
    return out


def validate_ranges(
    ranges: list[tuple[int, int]], strip_height: int, min_h: int = 40
) -> str | None:
    """Return a Vietnamese error message, or None when the ranges are valid."""
    prev_end = 0
    for i, (a, b) in enumerate(ranges):
        if a < 0 or b > strip_height:
            return f"Khung {i + 1} nằm ngoài dải ảnh (0–{strip_height})"
        if b - a < min_h:
            return f"Khung {i + 1} quá thấp ({b - a}px < {min_h}px)"
        if a < prev_end:
            return f"Khung {i + 1} chồng lấn hoặc sai thứ tự với khung trước"
        prev_end = b
    return None
