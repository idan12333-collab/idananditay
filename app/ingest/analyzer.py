"""Per-file analysis. Runs in worker processes, so it must be picklable and never raise.

Originals are opened read-only; nothing is ever written next to them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from app.ingest.hashing import perceptual_hashes, sha256_file
from app.ingest.imaging import oriented_size, save_thumbnail, to_rgb
from app.ingest.metadata import extract_metadata, resolve_capture_time
from app.vision.quality.classical import ClassicalQualityAnalyzer


@dataclass(frozen=True)
class AnalyzeConfig:
    thumbnails_dir: str
    thumbnail_size: int = 480
    thumbnail_quality: int = 85
    analysis_max_side: int = 1024
    blur_threshold: float = 40.0


# Phone screen resolutions (portrait devices): essentially never a coincidental real-photo size,
# since cameras store native sensor dimensions rather than pixel-exact device-screen crops. Safe to
# match regardless of image format.
_PHONE_SCREEN_SIZES = {
    (1170, 2532), (1179, 2556), (1284, 2778), (1290, 2796), (1125, 2436), (1242, 2688), (828, 1792),
    (750, 1334), (1242, 2208), (640, 1136), (1080, 1920), (1080, 2340), (1080, 2400), (1440, 3200),
    (1440, 2560), (1440, 3040), (720, 1280), (1080, 2220), (2048, 2732), (1668, 2388), (1640, 2360),
    (1620, 2160),
}
# Desktop/monitor resolutions: common enough as legitimate photo/video-frame JPEG dimensions too
# (e.g. 1920x1080, 1280x720), so only trusted for PNG/WEBP screenshots, not JPEG (ADR-023).
_DESKTOP_SCREEN_SIZES = {
    (1366, 768), (1920, 1080), (2560, 1440), (1280, 720), (1280, 800), (1440, 900), (1536, 864),
    (1600, 900), (1680, 1050), (1920, 1200), (2560, 1600), (2880, 1800), (3840, 2160),
}
_SCREEN_SIZES = _PHONE_SCREEN_SIZES | _DESKTOP_SCREEN_SIZES
_SCREENSHOT_NAME = re.compile(r"screen\s?shot|screenshot|צילום\s?מסך|スクリーンショット|captura", re.IGNORECASE)


def detect_screenshot(filename: str, fmt: str | None, has_camera_info: bool, w: int, h: int) -> tuple[bool, str | None]:
    if _SCREENSHOT_NAME.search(filename):
        return True, "filename"
    if has_camera_info:
        return False, None
    if fmt in ("PNG", "WEBP") and ((w, h) in _SCREEN_SIZES or (h, w) in _SCREEN_SIZES):
        return True, "screen-size image without camera EXIF"
    # No swapped-orientation check here: dimensions arrive EXIF-orientation-corrected, and a phone
    # portrait size swapped is exactly a common desktop landscape size (e.g. 1080x1920 <-> 1920x1080)
    # — checking both orders would flag ordinary landscape JPEGs as screenshots.
    if fmt == "JPEG" and (w, h) in _PHONE_SCREEN_SIZES:
        return True, "phone screen-size JPEG without camera EXIF"
    return False, None


def thumbnail_rel_path(content_hash: str) -> str:
    return f"{content_hash[:2]}/{content_hash}.jpg"


def analyze_file(path_str: str, config: AnalyzeConfig) -> dict:
    path = Path(path_str)
    result: dict = {"source_path": path_str, "indexed_at": datetime.now().isoformat(timespec="seconds")}
    try:
        st = path.stat()
        result["file_size"] = st.st_size
        result["file_mtime"] = st.st_mtime
        result["content_hash"] = sha256_file(path)

        with Image.open(path) as im:
            fmt = im.format
            result["format"] = fmt
            result["mime_type"] = Image.MIME.get(fmt or "") or None
            raw_w, raw_h = im.size
            meta = extract_metadata(im.getexif())
            if fmt == "JPEG":
                # Decode at reduced scale (much faster); still >= analysis size.
                im.draft("RGB", (config.analysis_max_side, config.analysis_max_side))
            im.load()
            try:
                oriented = ImageOps.exif_transpose(im) or im
            except Exception:  # malformed EXIF must not make a decodable photo unusable
                oriented = im
            rgb = to_rgb(oriented)

        width, height = oriented_size(raw_w, raw_h, meta.orientation)
        capture, source = resolve_capture_time(meta, path.name, st.st_mtime)

        quality = ClassicalQualityAnalyzer(config.blur_threshold, config.analysis_max_side).analyze(rgb)
        phash, dhash = perceptual_hashes(rgb)
        is_shot, shot_reason = detect_screenshot(path.name, fmt, meta.has_camera_info, width, height)

        thumb_rel = thumbnail_rel_path(result["content_hash"])
        save_thumbnail(rgb, Path(config.thumbnails_dir) / thumb_rel, config.thumbnail_size, config.thumbnail_quality)

        result.update(
            status="ok",
            error=None,
            phash=phash,
            dhash=dhash,
            width=width,
            height=height,
            orientation=meta.orientation,
            capture_time=capture.isoformat() if capture else None,
            capture_time_source=source,
            tz_offset=meta.tz_offset,
            camera_make=meta.camera_make,
            camera_model=meta.camera_model,
            gps_lat=meta.gps_lat,
            gps_lon=meta.gps_lon,
            gps_alt=meta.gps_alt,
            sharpness=quality.sharpness,
            brightness=quality.brightness,
            contrast=quality.contrast,
            dark_fraction=quality.dark_fraction,
            bright_fraction=quality.bright_fraction,
            exposure_issue=quality.exposure_issue,
            quality_score=quality.quality_score,
            is_blurry=int(quality.is_blurry),
            is_screenshot=int(is_shot),
            screenshot_reason=shot_reason,
            thumbnail_path=thumb_rel,
        )
    except Exception as exc:  # corrupted, unreadable, unsupported, cloud placeholder not downloadable...
        result.update(status="error", error=f"{type(exc).__name__}: {exc}"[:500])
    return result
