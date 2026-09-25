"""EXIF / capture-time / GPS extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from PIL import Image

EXIF_IFD = 0x8769
GPS_IFD = 0x8825

TAG_MAKE = 0x010F
TAG_MODEL = 0x0110
TAG_ORIENTATION = 0x0112
TAG_DATETIME = 0x0132
TAG_DATETIME_ORIGINAL = 0x9003
TAG_DATETIME_DIGITIZED = 0x9004
TAG_OFFSET_TIME_ORIGINAL = 0x9011

GPS_LAT_REF, GPS_LAT, GPS_LON_REF, GPS_LON, GPS_ALT_REF, GPS_ALT = 1, 2, 3, 4, 5, 6

MIN_YEAR = 1900


@dataclass
class PhotoMetadata:
    exif_time: datetime | None = None
    tz_offset: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    orientation: int = 1
    gps_lat: float | None = None
    gps_lon: float | None = None
    gps_alt: float | None = None

    @property
    def has_camera_info(self) -> bool:
        return bool(self.camera_make or self.camera_model)


def _clean_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    s = str(value).replace("\x00", "").strip()
    return s or None


def _valid_year(dt: datetime) -> bool:
    return MIN_YEAR <= dt.year <= datetime.now().year + 1


def parse_exif_datetime(value) -> datetime | None:
    s = _clean_str(value)
    if not s or s.startswith("0000"):
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y:%m:%d %H:%M"):
        try:
            dt = datetime.strptime(s[: len(datetime(2000, 1, 1).strftime(fmt))], fmt)
        except ValueError:
            continue
        return dt if _valid_year(dt) else None
    return None


def _to_float(v) -> float:
    if isinstance(v, tuple) and len(v) == 2:  # (numerator, denominator)
        return float(v[0]) / float(v[1]) if v[1] else 0.0
    return float(v)


def dms_to_decimal(dms, ref) -> float | None:
    try:
        parts = [_to_float(x) for x in dms]
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if len(parts) != 3 or any(p != p for p in parts):  # NaN check
        return None
    value = parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
    if (_clean_str(ref) or "").upper() in ("S", "W"):
        value = -value
    return value


def extract_metadata(exif: Image.Exif) -> PhotoMetadata:
    meta = PhotoMetadata()
    if not exif:
        return meta
    meta.camera_make = _clean_str(exif.get(TAG_MAKE))
    meta.camera_model = _clean_str(exif.get(TAG_MODEL))
    try:
        meta.orientation = int(exif.get(TAG_ORIENTATION, 1) or 1)
    except (TypeError, ValueError):
        meta.orientation = 1
    if meta.orientation not in range(1, 9):
        meta.orientation = 1

    try:
        exif_ifd = exif.get_ifd(EXIF_IFD)
    except Exception:  # malformed IFD
        exif_ifd = {}
    meta.exif_time = (
        parse_exif_datetime(exif_ifd.get(TAG_DATETIME_ORIGINAL))
        or parse_exif_datetime(exif_ifd.get(TAG_DATETIME_DIGITIZED))
        or parse_exif_datetime(exif.get(TAG_DATETIME))
    )
    meta.tz_offset = _clean_str(exif_ifd.get(TAG_OFFSET_TIME_ORIGINAL))

    try:
        gps = exif.get_ifd(GPS_IFD)
    except Exception:
        gps = {}
    if gps and GPS_LAT in gps and GPS_LON in gps:
        lat = dms_to_decimal(gps.get(GPS_LAT), gps.get(GPS_LAT_REF))
        lon = dms_to_decimal(gps.get(GPS_LON), gps.get(GPS_LON_REF))
        # (0, 0) is a common "no fix" placeholder.
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and (lat, lon) != (0, 0):
            meta.gps_lat, meta.gps_lon = round(lat, 7), round(lon, 7)
            if GPS_ALT in gps:
                try:
                    alt = _to_float(gps[GPS_ALT])
                    if gps.get(GPS_ALT_REF) in (1, b"\x01"):
                        alt = -alt
                    meta.gps_alt = round(alt, 2)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
    return meta


# e.g. IMG_20190512_101112.jpg, IMG-20190512-WA0001.jpg, 2019-05-12 10.11.12.jpg, PXL_20210304_101112345.jpg
_FILENAME_DATE = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
    r"(?:[-_ T.]?([01]\d|2[0-3])[-_.:]?([0-5]\d)[-_.:]?([0-5]\d))?"
)


def date_from_filename(name: str) -> datetime | None:
    for m in _FILENAME_DATE.finditer(name):
        y, mo, d, h, mi, s = m.groups()
        try:
            dt = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
        except ValueError:
            continue
        if _valid_year(dt):
            return dt
    return None


def resolve_capture_time(meta: PhotoMetadata, filename: str, mtime: float) -> tuple[datetime | None, str | None]:
    """Best-effort capture time and where it came from (exif > filename > file_mtime)."""
    if meta.exif_time:
        return meta.exif_time, "exif"
    from_name = date_from_filename(filename)
    if from_name:
        return from_name, "filename"
    try:
        return datetime.fromtimestamp(mtime).replace(microsecond=0), "file_mtime"
    except (OverflowError, OSError, ValueError):
        return None, None
