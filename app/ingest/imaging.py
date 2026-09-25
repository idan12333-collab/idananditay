"""Image decoding helpers (format registration, orientation, RGB conversion, thumbnails)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageFile

# Truncated/corrupted files must fail loudly, not decode to grey.
ImageFile.LOAD_TRUNCATED_IMAGES = False
# Allow large panoramas (default ~89 MP) while still guarding against decompression bombs.
Image.MAX_IMAGE_PIXELS = 400_000_000

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except Exception:  # pragma: no cover - depends on platform wheels
    HEIC_SUPPORTED = False

ROTATED_ORIENTATIONS = {5, 6, 7, 8}


def oriented_size(width: int, height: int, orientation: int) -> tuple[int, int]:
    return (height, width) if orientation in ROTATED_ORIENTATIONS else (width, height)


def to_rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB")


def save_thumbnail(img: Image.Image, dest: Path, size: int, quality: int) -> None:
    """Write atomically (parallel workers may render the same content hash)."""
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    thumb = img.copy()
    thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            thumb.save(f, "JPEG", quality=quality, optimize=True)
        os.replace(tmp, dest)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
