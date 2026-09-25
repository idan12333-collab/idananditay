"""Recursive folder scan. Read-only: only lists and stats files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger, log_event

logger = get_logger("ingest.scanner")

SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"})

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


def scan_folder(root: Path) -> list[ScannedFile]:
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
            try:
                st = path.stat()
            except OSError as exc:
                log_event(logger, "cannot stat file", level=30, path=str(path), error=str(exc))
                continue
            found.append(ScannedFile(path=path, size=st.st_size, mtime=st.st_mtime))
    return found
