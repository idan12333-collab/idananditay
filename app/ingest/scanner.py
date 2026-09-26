"""Recursive folder scan. Read-only: only lists and stats files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger, log_event

logger = get_logger("ingest.scanner")

SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"})
# Videos are not analyzed yet; they are only listed by the folder browser and may be excluded.
VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp", ".wmv", ".mts", ".m2ts", ".webm", ".mpg", ".mpeg"}
)
MEDIA_EXTENSIONS = SUPPORTED_EXTENSIONS | VIDEO_EXTENSIONS

# System/tool folders that never contain user photos.
IGNORED_DIR_NAMES = frozenset({"@eaDir", "$RECYCLE.BIN", "System Volume Information", "__MACOSX", ".thumbnails"})


@dataclass(frozen=True)
class ScannedFile:
    path: Path
    size: int
    mtime: float


def _ignored_dir(name: str) -> bool:
    return name.startswith(".") or name in IGNORED_DIR_NAMES


def is_supported(name: str) -> bool:
    return not name.startswith(".") and Path(name).suffix.lower() in SUPPORTED_EXTENSIONS


def exclusion_key(rel_path: str) -> str:
    """Comparison key for a path relative to the library root ('/'-separated; case-insensitive on Windows)."""
    key = rel_path.replace("\\", "/").strip("/")
    return key.casefold() if os.name == "nt" else key


def normalize_exclusion(root: Path, raw: str) -> str:
    """Validate one user-supplied exclusion (absolute, or relative to ``root``) -> relative '/' path.

    Purely lexical: the file itself is never touched. Raises ValueError for anything that is not a
    photo/video path strictly inside the library root.
    """
    raw = (raw or "").strip()
    if not raw or "\x00" in raw:
        raise ValueError("empty path")
    p = Path(raw)
    if p.is_absolute() or p.drive:
        try:
            p = p.relative_to(root)
        except ValueError:
            raise ValueError(f"not inside the library folder: {raw}") from None
    parts = p.parts
    if not parts or any(part in ("..", ".") for part in parts) or p.is_absolute() or p.drive:
        raise ValueError(f"invalid path: {raw}")
    if Path(parts[-1]).suffix.lower() not in MEDIA_EXTENSIONS:
        raise ValueError(f"not a photo or video: {raw}")
    return "/".join(parts)


def scan_folder(
    root: Path, excluded: frozenset[str] | set[str] = frozenset(), skipped: list[Path] | None = None
) -> list[ScannedFile]:
    """List supported photos under ``root``.

    ``excluded`` holds :func:`exclusion_key` values; matching files are skipped by name, before any
    stat/open, and (if given) appended to ``skipped``.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))

    def on_error(err: OSError) -> None:
        log_event(logger, "cannot read directory", level=30, path=getattr(err, "filename", "?"), error=str(err))

    found: list[ScannedFile] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=on_error):
        dirnames[:] = sorted(d for d in dirnames if not _ignored_dir(d))
        for name in sorted(filenames):
            if not is_supported(name):
                continue
            path = Path(dirpath) / name
            if excluded and exclusion_key(os.path.relpath(path, root)) in excluded:
                if skipped is not None:
                    skipped.append(path)
                continue  # excluded by the user: never stat-ed, read or analyzed
            try:
                st = path.stat()
            except OSError as exc:
                log_event(logger, "cannot stat file", level=30, path=str(path), error=str(exc))
                continue
            found.append(ScannedFile(path=path, size=st.st_size, mtime=st.st_mtime))
    return found
