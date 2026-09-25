"""HTTP API (JSON) for the local UI."""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps
from pydantic import BaseModel

from app import __version__
from app.db.repository import PHOTO_FILTERS, PHOTO_SORTS, Repository
from app.ingest.imaging import HEIC_SUPPORTED, to_rgb
from app.ingest.scanner import SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/api")

PREVIEW_MAX_SIDE = 1600


def _repo(request: Request) -> Repository:
    return request.app.state.repo


def _photo_out(p: dict) -> dict:
    p = dict(p)
    p["thumbnail_url"] = f"/api/photos/{p['id']}/thumbnail" if p.get("thumbnail_path") else None
    p["preview_url"] = f"/api/photos/{p['id']}/preview" if p.get("status") == "ok" else None
    # Human-readable signals (the UI shows these as badges).
    reasons = []
    if p.get("duplicate_group_id"):
        reasons.append("Best of duplicate group" if p.get("is_group_best") else "Duplicate — alternate")
    if p.get("is_blurry"):
        reasons.append("Blurry")
    if p.get("is_low_res"):
        reasons.append("Low resolution")
    if p.get("is_screenshot"):
        reasons.append("Screenshot")
    if p.get("exposure_issue"):
        reasons.append(p["exposure_issue"].capitalize())
    p["signals"] = reasons
    return p


class LibraryCreate(BaseModel):
    path: str
    name: str | None = None
    scan: bool = True


@router.get("/health")
def health(request: Request) -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "database": "ok" if request.app.state.db.ping() else "error",
        "heic_supported": HEIC_SUPPORTED,
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
    }


# ----------------------------------------------------------------- libraries
@router.get("/libraries")
def list_libraries(request: Request) -> list[dict]:
    repo = _repo(request)
    libs = repo.list_libraries()
    for lib in libs:
        lib["latest_job"] = repo.latest_job(lib["id"])
    return libs


@router.post("/libraries", status_code=201)
def create_library(body: LibraryCreate, request: Request) -> dict:
    raw = body.path.strip().strip('"')
    if not raw:
        raise HTTPException(400, "Path is required")
    path = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not path.is_dir():
        raise HTTPException(400, f"Folder not found: {raw}")
    root = path.resolve()
    repo = _repo(request)
    lib = repo.create_library(str(root), body.name or root.name or str(root))
    job = request.app.state.jobs.start_scan(lib["id"]) if body.scan else None
    return {"library": lib, "job": job}


def _get_library_or_404(request: Request, library_id: int) -> dict:
    lib = _repo(request).get_library(library_id)
    if lib is None:
        raise HTTPException(404, "Library not found")
    return lib


@router.post("/libraries/{library_id}/scan", status_code=202)
def rescan_library(library_id: int, request: Request) -> dict:
    _get_library_or_404(request, library_id)
    return request.app.state.jobs.start_scan(library_id)


@router.delete("/libraries/{library_id}")
def delete_library(library_id: int, request: Request) -> dict:
    """Deletes all DERIVED data for the library (index, thumbnails). Original photos are never touched."""
    _get_library_or_404(request, library_id)
    if _repo(request).active_job(library_id):
        raise HTTPException(409, "A scan is running for this library; cancel it first")
    orphaned = _repo(request).delete_library(library_id)
    thumbs_dir = request.app.state.settings.thumbnails_dir
    removed = 0
    for rel in orphaned:
        try:
            (thumbs_dir / rel).unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return {"deleted": True, "thumbnails_removed": removed}


@router.get("/libraries/{library_id}/stats")
def library_stats(library_id: int, request: Request) -> dict:
    lib = _get_library_or_404(request, library_id)
    repo = _repo(request)
    return {"library": lib, "stats": repo.library_stats(library_id), "latest_job": repo.latest_job(library_id)}


@router.get("/libraries/{library_id}/duplicates")
def duplicate_groups(
    library_id: int, request: Request, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=200)
) -> dict:
    _get_library_or_404(request, library_id)
    groups, total = _repo(request).list_duplicate_groups(library_id, offset, limit)
    for g in groups:
        g["members"] = [_photo_out(m) for m in g["members"]]
    return {"total": total, "offset": offset, "groups": groups}


# ---------------------------------------------------------------------- jobs
@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    job = _repo(request).get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict:
    return {"cancelling": request.app.state.jobs.cancel(job_id)}


# -------------------------------------------------------------------- photos
@router.get("/photos")
def list_photos(
    request: Request,
    library_id: int,
    filter: str = "all",
    year: int | None = None,
    sort: str = "date",
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    if filter not in PHOTO_FILTERS:
        raise HTTPException(400, f"Unknown filter. Use one of: {', '.join(PHOTO_FILTERS)}")
    if sort not in PHOTO_SORTS:
        raise HTTPException(400, f"Unknown sort. Use one of: {', '.join(PHOTO_SORTS)}")
    items, total = _repo(request).list_photos(library_id, filter, year, sort, offset, limit)
    return {"total": total, "offset": offset, "items": [_photo_out(p) for p in items]}


def _get_photo_or_404(request: Request, photo_id: int) -> dict:
    p = _repo(request).get_photo(photo_id)
    if p is None:
        raise HTTPException(404, "Photo not found")
    return p


@router.get("/photos/{photo_id}")
def get_photo(photo_id: int, request: Request) -> dict:
    p = _photo_out(_get_photo_or_404(request, photo_id))
    p["duplicates"] = (
        [_photo_out(m) for m in _repo(request).get_group_members(p["duplicate_group_id"]) if m["id"] != photo_id]
        if p.get("duplicate_group_id")
        else []
    )
    return p


@router.get("/photos/{photo_id}/thumbnail")
def photo_thumbnail(photo_id: int, request: Request):
    p = _get_photo_or_404(request, photo_id)
    if not p.get("thumbnail_path"):
        raise HTTPException(404, "No thumbnail")
    path = request.app.state.settings.thumbnails_dir / p["thumbnail_path"]
    if not path.is_file():
        raise HTTPException(404, "Thumbnail file missing (rescan to regenerate)")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.get("/photos/{photo_id}/preview")
def photo_preview(photo_id: int, request: Request):
    """Larger JPEG rendered on the fly from the original (read-only; works for HEIC too)."""
    p = _get_photo_or_404(request, photo_id)
    src = Path(p["source_path"])
    if p["status"] != "ok" or not src.is_file():
        raise HTTPException(404, "Original not available")
    try:
        with Image.open(src) as im:
            if im.format == "JPEG":
                im.draft("RGB", (PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE))
            im.load()
            img = to_rgb(ImageOps.exif_transpose(im) or im)
        img.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
    except Exception as exc:
        raise HTTPException(500, f"Cannot render preview: {type(exc).__name__}") from exc
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


# -------------------------------------------------------------------- system
_PICK_FOLDER_SCRIPT = """
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
path = filedialog.askdirectory(title='Choose a photo folder', mustexist=True)
sys.stdout.buffer.write((path or '').encode('utf-8'))
"""


@router.post("/system/pick-folder")
def pick_folder() -> dict:
    """Opens the native folder dialog on this computer (local app only)."""
    try:
        out = subprocess.run(
            [sys.executable, "-c", _PICK_FOLDER_SCRIPT], capture_output=True, timeout=600, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(500, f"Folder dialog unavailable: {type(exc).__name__}") from exc
    path = out.stdout.decode("utf-8", errors="replace").strip()
    return {"path": str(Path(path)) if path else None}
