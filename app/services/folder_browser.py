"""Read-only folder browser used by the "choose a photo folder" dialog (ADR-014).

Security/privacy rules enforced here (the API layer adds nothing but HTTP):

* Only absolute paths on the allowed roots (local fixed/removable drives, or ``Settings.browse_roots``)
  are accepted. UNC/network paths, device paths (``\\\\?\\``, ``\\\\.\\``), NTFS alternate data streams
  and NUL bytes are rejected *before* touching the disk; the resolved path (after symlinks/junctions)
  must still be inside a root.
* Listing a folder only reads directory entries. Files that are not images/videos are skipped by
  extension without being stat-ed or opened. Videos are never opened.
* Only image files are ever decoded (for a small in-memory thumbnail). Originals are opened read-only.
* OneDrive "online-only" placeholders are detected from the directory entry attributes and never
  opened, so browsing never triggers a download.
"""

from __future__ import annotations

import io
import os
import stat as stat_mod
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from app.ingest.imaging import to_rgb
from app.ingest.scanner import IGNORED_DIR_NAMES, SUPPORTED_EXTENSIONS, VIDEO_EXTENSIONS, exclusion_key

IMAGE_EXTENSIONS = SUPPORTED_EXTENSIONS

BROWSE_THUMB_SIDE = 256
MAX_PAGE = 500

IS_WINDOWS = sys.platform == "win32"

# Windows file attributes (winnt.h).
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
CLOUD_ONLY_MASK = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS


class BrowseError(Exception):
    """Path rejected or unreadable. ``status`` is the HTTP status the API should return."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class CloudOnlyError(BrowseError):
    def __init__(self) -> None:
        super().__init__("File is stored only in the cloud (OneDrive); not downloaded for a preview", 409)


def media_kind(name: str) -> str | None:
    if name.startswith("."):
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def is_cloud_only(attributes: int) -> bool:
    return bool(attributes & CLOUD_ONLY_MASK)


def _attributes(st: os.stat_result) -> int:
    return getattr(st, "st_file_attributes", 0)


# ------------------------------------------------------------------- roots
def _local_drives() -> list[Path]:
    if not IS_WINDOWS:
        return [Path("/")]
    import ctypes

    get_type = ctypes.windll.kernel32.GetDriveTypeW
    drives = os.listdrives() if hasattr(os, "listdrives") else [f"{c}:\\" for c in "CDEFGHIJKLMNOPQRSTUVWXYZ"]
    # 2 = removable, 3 = fixed. Network (4), CD-ROM (5) and RAM disks are left out on purpose.
    return [Path(d) for d in drives if get_type(d) in (2, 3) and os.path.isdir(d)]


def allowed_roots(configured: list[Path] | None = None) -> list[Path]:
    roots = configured or _local_drives()
    return [Path(r).resolve() for r in roots]


def _known_folder(value_name: str, fallback: Path) -> Path:
    if IS_WINDOWS:
        try:
            import winreg

            key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                raw, _ = winreg.QueryValueEx(k, value_name)
            return Path(os.path.expandvars(raw))
        except OSError:
            pass
    return fallback


def shortcuts(roots: list[Path]) -> list[dict]:
    """Quick-access locations (only those that exist and are inside the allowed roots)."""
    home = Path.home()
    candidates = [
        ("תמונות", "pictures", _known_folder("My Pictures", home / "Pictures")),
        ("שולחן העבודה", "desktop", _known_folder("Desktop", home / "Desktop")),
        ("OneDrive", "cloud", Path(os.environ["OneDrive"]) if os.environ.get("OneDrive") else None),
        ("תיקיית המשתמש", "home", home),
    ]
    out, seen = [], set()
    for label, kind, path in candidates:
        if path is None or not path.is_dir():
            continue
        p = path.resolve()
        if str(p).casefold() in seen or _root_of(p, roots) is None:
            continue
        seen.add(str(p).casefold())
        out.append({"label": label, "kind": kind, "path": str(p)})
    for d in roots:
        out.append({"label": str(d), "kind": "drive", "path": str(d)})
    return out


def _root_of(path: Path, roots: list[Path]) -> Path | None:
    for r in roots:
        if path == r or path.is_relative_to(r):
            return r
    return None


# -------------------------------------------------------------- validation
def _check_raw(raw: str) -> str:
    raw = (raw or "").strip().strip('"')
    if not raw:
        raise BrowseError("Path is required")
    if "\x00" in raw:
        raise BrowseError("Invalid path")
    if IS_WINDOWS:
        norm = raw.replace("/", "\\")
        if norm.startswith("\\\\"):
            raise BrowseError("Network and device paths are not supported here", 403)
        if len(norm) < 3 or norm[1] != ":" or norm[2] != "\\" or not norm[0].isalpha():
            raise BrowseError("An absolute path such as C:\\Photos is required")
        if ":" in norm[2:]:
            raise BrowseError("Invalid path")  # NTFS alternate data stream
    elif not raw.startswith("/"):
        raise BrowseError("An absolute path is required")
    return raw


def resolve_inside_roots(raw: str, roots: list[Path]) -> Path:
    raw = _check_raw(raw)
    try:
        path = Path(raw).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise BrowseError("Not found", 404) from exc
    # A symlink/junction could point to a network share or outside the roots.
    if IS_WINDOWS and str(path).startswith("\\\\"):
        raise BrowseError("Network and device paths are not supported here", 403)
    if _root_of(path, roots) is None:
        raise BrowseError("Outside the folders that can be browsed", 403)
    return path


def _hidden_dir(name: str, st: os.stat_result | None) -> bool:
    if name.startswith(".") or name in IGNORED_DIR_NAMES or name.startswith("$"):
        return True
    return bool(st and _attributes(st) & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


def media_version(st: os.stat_result) -> str:
    return f"{st.st_size:x}-{st.st_mtime_ns:x}"


# ----------------------------------------------------------------- listing
@dataclass
class MediaEntry:
    name: str
    path: str
    kind: str
    size: int
    version: str
    cloud_only: bool


def list_folder(raw: str, roots: list[Path], offset: int = 0, limit: int = 200) -> dict:
    folder = resolve_inside_roots(raw, roots)
    if not folder.is_dir():
        raise BrowseError("Not a folder")
    folders: list[dict] = []
    media: list[MediaEntry] = []
    try:
        entries = list(os.scandir(folder))
    except PermissionError as exc:
        raise BrowseError("No permission to open this folder", 403) from exc
    except OSError as exc:
        raise BrowseError(f"Cannot read folder: {exc.strerror or exc}", 400) from exc
    for e in entries:
        try:
            if e.is_dir():  # follows links; the target is re-validated when navigated to
                st = e.stat(follow_symlinks=False) if IS_WINDOWS else None  # cached from the listing
                if not _hidden_dir(e.name, st):
                    folders.append({"name": e.name, "path": os.path.join(str(folder), e.name)})
                continue
            kind = media_kind(e.name)
            if kind is None:
                continue  # never stat or open files that are not photos/videos
            st = e.stat()
            if not stat_mod.S_ISREG(st.st_mode):
                continue
        except OSError:
            continue
        media.append(
            MediaEntry(
                name=e.name, path=e.path, kind=kind, size=st.st_size,
                version=media_version(st), cloud_only=is_cloud_only(_attributes(st)),
            )
        )
    folders.sort(key=lambda f: f["name"].casefold())
    media.sort(key=lambda m: m.name.casefold())
    limit = max(1, min(limit, MAX_PAGE))
    offset = max(0, offset)
    root = _root_of(folder, roots)
    crumbs, p = [], folder
    while True:
        crumbs.append({"name": p.name or str(p), "path": str(p)})
        if p == root or p.parent == p:
            break
        p = p.parent
    return {
        "path": str(folder),
        "parent": None if folder == root else str(folder.parent),
        "breadcrumbs": list(reversed(crumbs)),
        "folders": folders,
        "counts": {
            "folders": len(folders),
            "images": sum(m.kind == "image" for m in media),
            "videos": sum(m.kind == "video" for m in media),
            "cloud_only": sum(m.cloud_only for m in media),
        },
        "total": len(media),
        "offset": offset,
        "items": media[offset : offset + limit],
    }


# --------------------------------------------------------------- thumbnail
def render_thumbnail(raw: str, roots: list[Path], side: int = BROWSE_THUMB_SIDE) -> tuple[bytes, str]:
    """Small JPEG of an image file (read-only). Returns (jpeg bytes, version)."""
    if media_kind(os.path.basename(raw.rstrip("\\/"))) != "image":
        raise BrowseError("Only image files have previews", 415)  # checked before touching the disk
    path = resolve_inside_roots(raw, roots)
    if media_kind(path.name) != "image":  # e.g. a link named x.jpg pointing to a non-image
        raise BrowseError("Only image files have previews", 415)
    st = path.stat()
    if not stat_mod.S_ISREG(st.st_mode):
        raise BrowseError("Not a file", 415)
    if is_cloud_only(_attributes(st)):
        raise CloudOnlyError()
    try:
        img = decode_preview(path, side)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
    except Exception as exc:
        raise BrowseError(f"Cannot read image: {type(exc).__name__}", 422) from exc
    return buf.getvalue(), media_version(st)


def decode_preview(path: Path, side: int) -> Image.Image:
    with open(path, "rb") as f, Image.open(f) as im:  # "rb": the original is never written
        if im.format == "JPEG":
            im.draft("RGB", (side * 2, side * 2))
        im.load()
        img = to_rgb(ImageOps.exif_transpose(im) or im)
    img.thumbnail((side, side), Image.Resampling.LANCZOS)
    return img


# ----------------------------------------------------------------- summary
def summarize_folder(raw: str, roots: list[Path], exclude: list[str]) -> dict:
    """Recursive pre-scan counts for the "choose folder" summary (ADR-016).

    Uses the scanner's folder rules and looks at names only (no stat/open of any file), so the
    numbers match what a scan would pick up. ``exclude`` = paths (absolute or relative to the folder)
    the user marked; only those that actually exist under the folder are counted as excluded.
    """
    from app.ingest.scanner import _ignored_dir, is_supported, normalize_exclusion

    folder = resolve_inside_roots(raw, roots)
    if not folder.is_dir():
        raise BrowseError("Not a folder")
    keys = set()
    for p in exclude:
        try:
            keys.add(exclusion_key(normalize_exclusion(folder, p)))
        except ValueError:
            continue  # marked outside this folder: not part of this scan
    counts = {"images": 0, "videos": 0, "excluded_images": 0, "excluded_videos": 0}
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [d for d in dirnames if not _ignored_dir(d)]
        for name in filenames:
            if is_supported(name):
                kind = "images"
            elif media_kind(name) == "video":
                kind = "videos"
            else:
                continue
            counts[kind] += 1
            if keys and exclusion_key(os.path.relpath(os.path.join(dirpath, name), folder)) in keys:
                counts[f"excluded_{kind}"] += 1
    counts["images_to_scan"] = counts["images"] - counts["excluded_images"]
    return {"path": str(folder), **counts}
