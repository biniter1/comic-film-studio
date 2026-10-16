"""Synthetic comic pages for tests (no real comic files in the repo)."""

from pathlib import Path

import numpy as np
from PIL import Image

W = 600


def noise_block(h: int, w: int = W, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(30, 225, size=(h, w, 3), dtype=np.uint8)


def gutter(h: int, color: int = 255, w: int = W) -> np.ndarray:
    return np.full((h, w, 3), color, dtype=np.uint8)


def page(parts: list[np.ndarray]) -> Image.Image:
    return Image.fromarray(np.concatenate(parts, axis=0))


def save(img: Image.Image, path: Path, fmt: str = "PNG") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, fmt)
    return path


def two_pages_with_split_panel(tmp: Path) -> list[Path]:
    """Page 1: panel A (400) | white gutter | panel B top half (300, touches bottom edge)
    Page 2: panel B bottom half (300, touches top edge) | black gutter | text band (60) | white | panel C (500)
    Expected frames: A, B (reassembled across pages), C (with the text band merged in)."""
    p1 = page([gutter(30), noise_block(400, seed=1), gutter(50), noise_block(300, seed=2)])
    p2 = page(
        [
            noise_block(300, seed=3),
            gutter(40, 0),
            noise_block(60, seed=4),
            gutter(40),
            noise_block(500, seed=5),
            gutter(30),
        ]
    )
    return [save(p1, tmp / "1.png"), save(p2, tmp / "2.png")]
