from pathlib import Path

from PIL import Image

from app.frames import strip as S
from tests.imgutil import gutter, noise_block, page, save, two_pages_with_split_panel


def _strip(paths: list[Path]) -> S.Strip:
    rows = []
    for i, p in enumerate(paths):
        with Image.open(p) as im:
            rows.append((f"P{i}", p, im.width, im.height))
    return S.build_strip(rows)


def test_four_blocks_white_and_black_gutters(tmp_path):
    img = page(
        [
            noise_block(300, seed=1),
            gutter(40),
            noise_block(250, seed=2),
            gutter(40, 0),
            noise_block(400, seed=3),
            gutter(25),
            noise_block(200, seed=4),
        ]
    )
    strip = _strip([save(img, tmp_path / "p.png")])
    frames = S.detect_frames(strip)
    assert [b - a for a, b in frames] == [300, 250, 400, 200]


def test_thin_text_band_merges_into_next_frame(tmp_path):
    img = page(
        [noise_block(300), gutter(40), noise_block(60, seed=9), gutter(30), noise_block(400)]
    )
    frames = S.detect_frames(_strip([save(img, tmp_path / "p.png")]))
    assert len(frames) == 2
    a, b = frames[1]
    assert b - a == 60 + 30 + 400  # band + gap + panel


def test_panel_split_across_two_pages_is_reassembled(tmp_path):
    strip = _strip(two_pages_with_split_panel(tmp_path))
    frames = S.detect_frames(strip)
    heights = [b - a for a, b in frames]
    assert heights[0] == 400
    assert heights[1] == 600, "panel B (300 + 300 across the page break) must be ONE frame"
    assert len(frames) == 3
    # crop of the reassembled frame spans both pages without seams of white
    crop = S.crop_frame(strip, *frames[1])
    assert crop.size == (600, 600)


def test_pages_with_different_widths_are_scaled(tmp_path):
    a = save(page([noise_block(400, w=600)]), tmp_path / "a.png")
    b = save(page([noise_block(200, w=300)]), tmp_path / "b.png")
    strip = _strip([a, b])
    assert strip.width == 600
    assert strip.pages[1].scaled_h == 400
    assert strip.height == 800


def test_long_continuous_art_is_split():
    import numpy as np

    mask = np.zeros(5000, dtype=bool)  # 5000 px of art without any gutter
    frames = S.detect_frames(S.Strip(600, []), mask=mask, max_frame_h=2400)
    assert len(frames) == 3 and frames[0][0] == 0 and frames[-1][1] == 5000


def test_validate_ranges():
    assert S.validate_ranges([(0, 100), (100, 300)], 300) is None
    assert "chồng lấn" in S.validate_ranges([(0, 200), (150, 300)], 300)
    assert "quá thấp" in S.validate_ranges([(0, 10)], 300)
    assert "ngoài" in S.validate_ranges([(0, 400)], 300)
