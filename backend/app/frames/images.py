"""Image validation and previews (Pillow)."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 30 * 1024 * 1024
MIN_PAGE_WIDTH = 300
PREVIEW_WIDTH = 400
ALLOWED_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}

# Pillow's decompression-bomb guard: webtoon pages are tall but not absurd
Image.MAX_IMAGE_PIXELS = 200_000_000


@dataclass
class ImageCheck:
    ok: bool
    reason: str | None = None
    width: int = 0
    height: int = 0
    fmt: str | None = None
    ext: str | None = None
    sha256: str | None = None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_image(path: Path, min_width: int = MIN_PAGE_WIDTH) -> ImageCheck:
    """Validate by content (never trust the extension)."""
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        return ImageCheck(False, f"File quá lớn ({size // (1024 * 1024)}MB > 30MB)")
    if size == 0:
        return ImageCheck(False, "File rỗng")
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:  # verify() invalidates the object: reopen to read
            im.load()
            fmt = im.format or ""
            w, h = im.size
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as e:
        return ImageCheck(False, f"Không phải ảnh hợp lệ hoặc ảnh bị hỏng ({type(e).__name__})")
    except Image.DecompressionBombError:
        return ImageCheck(False, "Ảnh quá lớn (vượt giới hạn số điểm ảnh)")
    if fmt not in ALLOWED_FORMATS:
        return ImageCheck(False, f"Định dạng không hỗ trợ: {fmt or 'không rõ'} (chỉ JPEG/PNG/WEBP)")
    if w < min_width:
        return ImageCheck(False, f"Ảnh quá nhỏ (rộng {w}px < {min_width}px)", w, h, fmt)
    return ImageCheck(True, None, w, h, fmt, ALLOWED_FORMATS[fmt], sha256_file(path))


def make_preview(src: Path, dst: Path, width: int = PREVIEW_WIDTH) -> tuple[int, int]:
    with Image.open(src) as im:
        im = im.convert("RGB")
        h = max(1, round(im.height * width / im.width))
        im.resize((width, h), Image.LANCZOS).save(dst, "JPEG", quality=82)
        return width, h
