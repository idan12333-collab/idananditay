"""HTTP API (JSON) for the local UI."""

from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, ImageOps
from pydantic import BaseModel

from app import __version__
from app.core.instance import APP_NAME, BUILD_ID, process_id
from app.curation import seed as seed_sample
from app.db.repository import (
    CURATION_WORTHINESS, PHOTO_FILTERS, PHOTO_SORTS, REVIEW_REASONS, REVIEW_VERDICTS, Repository,
)
from app.ingest.imaging import HEIC_SUPPORTED, to_rgb
from app.ingest.scanner import SUPPORTED_EXTENSIONS, normalize_exclusion
from app.printing.suitability import PrintPolicy, assess
from app.vision.quality import classical

router = APIRouter(prefix="/api")

PREVIEW_MAX_SIDE = 1600

# Image URLs carry a content version (?v=<hash prefix>). A versioned URL always maps to the same
# bytes, so it may be cached forever; anything else must be revalidated. This is what stops the
# browser from showing a cached image of a different photo that once had the same URL.
IMMUTABLE_CACHE = "private, max-age=31536000, immutable"
REVALIDATE_CACHE = "no-cache"


def _media_version(p: dict) -> str:
    return (p.get("content_hash") or "")[:16]


def _media_headers(p: dict, requested_version: str | None) -> dict[str, str]:
    current = _media_version(p)
    cacheable = bool(current) and requested_version == current
    return {"Cache-Control": IMMUTABLE_CACHE if cacheable else REVALIDATE_CACHE, "ETag": f'"{p.get("content_hash")}"'}


def _repo(request: Request) -> Repository:
    return request.app.state.repo


def _photo_out(p: dict, policy: PrintPolicy) -> dict:
    p = dict(p)
    v = _media_version(p)
    p["thumbnail_url"] = f"/api/photos/{p['id']}/thumbnail?v={v}" if p.get("thumbnail_path") else None
    p["preview_url"] = f"/api/photos/{p['id']}/preview?v={v}" if p.get("status") == "ok" else None
    # Human-readable signals (the UI shows these as badges).
    reasons = []
    if p.get("duplicate_group_id"):
        reasons.append("Best of duplicate group" if p.get("is_group_best") else "Duplicate — alternate")
    if p.get("is_blurry"):
        reasons.append("Blurry")
    if p.get("width") and p.get("height") and policy.is_extremely_low(p["width"], p["height"]):
        reasons.append("Extremely low resolution")  # the only resolution warning (ADR-017)
    if p.get("is_screenshot"):
        reasons.append("Screenshot")
    if p.get("exposure_issue"):
        reasons.append(p["exposure_issue"].capitalize())
    p["signals"] = reasons
    return p


MAX_EXCLUSIONS = 100_000


class LibraryCreate(BaseModel):
    path: str
    name: str | None = None
    scan: bool = True
    # Files not to include (ADR-016): absolute or relative to `path`. None = keep the library's
    # current list (e.g. a path typed by hand); [] = clear it.
    exclude: list[str] | None = None


@router.get("/health")
def health(request: Request) -> dict:
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": __version__,
        "build": BUILD_ID,  # fingerprint of the running code — shows which copy of the app answers
        "pid": process_id(),
        "dev_instance": os.environ.get("AI_ALBUM_DEV_INSTANCE"),  # dev auto-reload only (ADR-020)
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
    exclusions: list[str] | None = None
    if body.exclude is not None:
        if len(body.exclude) > MAX_EXCLUSIONS:
            raise HTTPException(400, f"Too many excluded files (max {MAX_EXCLUSIONS})")
        try:  # lexical validation only — excluded files are never touched
            exclusions = [normalize_exclusion(root, p) for p in body.exclude]
        except ValueError as exc:
            raise HTTPException(400, f"Invalid excluded file: {exc}") from exc
    repo = _repo(request)
    lib = repo.create_library(str(root), body.name or root.name or str(root))
    if exclusions is not None:
        if repo.active_job(lib["id"]):
            raise HTTPException(409, "A scan is running for this library; wait for it or cancel it first")
        repo.set_exclusions(lib["id"], exclusions)
    job = request.app.state.jobs.start_scan(lib["id"]) if body.scan else None
    return {"library": lib, "job": job, "exclusions": len(repo.get_exclusions(lib["id"]))}


@router.get("/exclusions")
def list_exclusions(request: Request) -> list[dict]:
    """Every library's exclusion list, as absolute paths (the folder browser pre-marks them)."""
    repo = _repo(request)
    out = []
    for lib in repo.list_libraries():
        rels = repo.get_exclusions(lib["id"])
        if rels:
            root = Path(lib["root_path"])
            out.append({"library_id": lib["id"], "root_path": lib["root_path"],
                        "paths": [str(root.joinpath(*r.split("/"))) for r in rels]})
    return out


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
    # Privacy: derived data must go with the library. Also sweep thumbnails no photo references any
    # more (left by older versions, or by rescans of edited files) — but never while a scan is running,
    # because a scan writes a thumbnail before its database row exists.
    if not _repo(request).any_active_job():
        referenced = _repo(request).referenced_thumbnails()
        for f in thumbs_dir.rglob("*.jpg"):
            if f.relative_to(thumbs_dir).as_posix() not in referenced:
                try:
                    f.unlink()
                    removed += 1
                except OSError:
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
        g["members"] = [_photo_out(m, _repo(request).print_policy) for m in g["members"]]
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
    return {"total": total, "offset": offset, "items": [_photo_out(p, _repo(request).print_policy) for p in items]}


def _get_photo_or_404(request: Request, photo_id: int) -> dict:
    p = _repo(request).get_photo(photo_id)
    if p is None:
        raise HTTPException(404, "Photo not found")
    return p


@router.get("/photos/{photo_id}")
def get_photo(photo_id: int, request: Request) -> dict:
    """Everything the review viewer shows: metadata, automatic analysis, print suitability, human label."""
    repo = _repo(request)
    p = _photo_out(_get_photo_or_404(request, photo_id), repo.print_policy)
    p["duplicates"] = (
        [_photo_out(m, repo.print_policy) for m in repo.get_group_members(p["duplicate_group_id"]) if m["id"] != photo_id]
        if p.get("duplicate_group_id")
        else []
    )
    group = repo.get_duplicate_group(p["duplicate_group_id"]) if p.get("duplicate_group_id") else None
    if group:
        group["members"] = [_photo_out(m, repo.print_policy) for m in group["members"]]
    p["duplicate_group"] = group  # the whole group incl. this photo, the kept one and the automatic choice
    p["original_url"] = f"/api/photos/{photo_id}/original?v={_media_version(p)}" if p.get("status") == "ok" else None
    p["print"] = assess(p.get("width"), p.get("height"), repo.print_policy)
    p["analysis"] = _analysis(p, request.app.state.settings.blur_threshold)
    ext_format = _EXT_FORMAT.get(Path(p["source_path"]).suffix.lower())
    p["extension_matches_format"] = ext_format is None or p.get("format") is None or ext_format == p["format"]
    p["review"] = repo.get_review(p.get("content_hash"))
    return p


_EXT_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".heic": "HEIF", ".heif": "HEIF"}


def _analysis(p: dict, blur_threshold: float) -> dict | None:
    """Automatic measurements next to the rules applied to them, so a reviewer can judge each flag."""
    if p.get("sharpness") is None:
        return None
    return {
        "analyzer": classical.ClassicalQualityAnalyzer.name,
        "sharpness": {"value": p["sharpness"], "blur_threshold": blur_threshold, "is_blurry": bool(p["is_blurry"])},
        "exposure": {
            "brightness": p["brightness"],
            "dark_fraction": p["dark_fraction"],
            "bright_fraction": p["bright_fraction"],
            "issue": p["exposure_issue"],
            "rules": {
                "underexposed": f"brightness < {classical.UNDEREXPOSED_MEAN} "
                                f"or dark > {classical.UNDEREXPOSED_DARK_FRACTION:.0%}",
                "overexposed": f"brightness > {classical.OVEREXPOSED_MEAN} "
                               f"or bright > {classical.OVEREXPOSED_BRIGHT_FRACTION:.0%}",
            },
        },
        "contrast": p["contrast"],
        "screenshot": {"is_screenshot": bool(p["is_screenshot"]), "reason": p.get("screenshot_reason")},
        "quality": {
            "score": p["quality_score"],
            "components": classical.quality_components(p["sharpness"], p["exposure_issue"], p["contrast"]),
            "weights": classical.SCORE_WEIGHTS,
        },
    }


def _auto_snapshot(p: dict, policy: PrintPolicy) -> dict:
    """The automatic verdicts as they were when the human labeled the photo (for later evaluation)."""
    in_group = bool(p.get("duplicate_group_id"))
    return {
        "analyzer": classical.ClassicalQualityAnalyzer.name,
        "is_blurry": bool(p.get("is_blurry")),
        "sharpness": p.get("sharpness"),
        "exposure_issue": p.get("exposure_issue"),
        "is_screenshot": bool(p.get("is_screenshot")),
        "extreme_low_res": bool(p.get("width") and p.get("height") and policy.is_extremely_low(p["width"], p["height"])),
        "width": p.get("width"),
        "height": p.get("height"),
        "quality_score": p.get("quality_score"),
        "duplicate": ("best" if p.get("is_group_best") else "alternate") if in_group else None,
        "print_policy": policy.to_dict(),
    }


class ReviewIn(BaseModel):
    verdict: str
    reasons: list[str] = []
    note: str | None = None


@router.put("/photos/{photo_id}/review")
def set_review(photo_id: int, body: ReviewIn, request: Request) -> dict:
    """Store a human label. Never touches the automatic analysis of the photo (ADR-018)."""
    repo = _repo(request)
    p = _get_photo_or_404(request, photo_id)
    if p["status"] != "ok":
        raise HTTPException(400, "Only analyzed photos can be reviewed")
    if body.verdict not in REVIEW_VERDICTS:
        raise HTTPException(400, f"verdict must be one of: {', '.join(REVIEW_VERDICTS)}")
    unknown = sorted(set(body.reasons) - set(REVIEW_REASONS))
    if unknown:
        raise HTTPException(400, f"Unknown reasons {unknown}. Use: {', '.join(REVIEW_REASONS)}")
    if body.note and len(body.note) > 2000:
        raise HTTPException(400, "Note is too long")
    return repo.set_review(p, body.verdict, body.reasons, body.note, _auto_snapshot(p, repo.print_policy))


@router.delete("/photos/{photo_id}/review")
def delete_review(photo_id: int, request: Request) -> dict:
    p = _get_photo_or_404(request, photo_id)
    return {"deleted": _repo(request).delete_review(p.get("content_hash"))}


@router.get("/libraries/{library_id}/review/stats")
def review_stats(library_id: int, request: Request) -> dict:
    _get_library_or_404(request, library_id)
    return _repo(request).review_stats(library_id)


@router.get("/libraries/{library_id}/filter/summary")
def filter_summary(library_id: int, request: Request) -> dict:
    """What the automatic filter did (per reason) and what the human feedback changed."""
    _get_library_or_404(request, library_id)
    return _repo(request).filter_summary(library_id)


def _no_scan_running(request: Request, library_id: int) -> None:
    # Checked BEFORE storing a pick, so a refused request changes nothing.
    if _repo(request).active_job(library_id):
        raise HTTPException(409, "A scan is running for this library; try again when it finishes")


def _regroup(request: Request, library_id: int) -> None:
    from app.ingest.pipeline import IngestionPipeline

    IngestionPipeline(request.app.state.settings, _repo(request)).update_duplicates(library_id)


def _group_out(request: Request, photo_id: int) -> dict:
    repo = _repo(request)
    p = repo.get_photo(photo_id)
    members = repo.get_group_members(p["duplicate_group_id"]) if p and p.get("duplicate_group_id") else []
    group = repo.get_duplicate_group(p["duplicate_group_id"]) if p and p.get("duplicate_group_id") else None
    return {"group_id": p.get("duplicate_group_id") if p else None,
            "best_photo_id": group["best_photo_id"] if group else None,
            "auto_best_photo_id": group["auto_best_photo_id"] if group else None,
            "members": [_photo_out(m, repo.print_policy) for m in members]}


@router.put("/photos/{photo_id}/keep")
def keep_in_group(photo_id: int, request: Request) -> dict:
    """The user chooses this photo as the one to keep in its duplicate group. Nothing is deleted."""
    p = _get_photo_or_404(request, photo_id)
    if not p.get("duplicate_group_id"):
        raise HTTPException(400, "Photo is not in a duplicate group")
    _no_scan_running(request, p["library_id"])
    _repo(request).set_duplicate_pick(p["duplicate_group_id"], p)
    _regroup(request, p["library_id"])
    return _group_out(request, photo_id)


@router.delete("/photos/{photo_id}/keep")
def reset_group_pick(photo_id: int, request: Request) -> dict:
    """Back to the automatic choice for this photo's duplicate group."""
    p = _get_photo_or_404(request, photo_id)
    if p.get("duplicate_group_id"):
        _no_scan_running(request, p["library_id"])
        _repo(request).clear_duplicate_picks(p["duplicate_group_id"])
        _regroup(request, p["library_id"])
    return _group_out(request, photo_id)


@router.get("/libraries/{library_id}/review/export")
def export_reviews(library_id: int, request: Request, format: str = "json"):
    """The human-labeled evaluation set of this library (labels + current automatic analysis)."""
    _get_library_or_404(request, library_id)
    rows = _repo(request).export_reviews(library_id)
    disposition = {"Content-Disposition": f'attachment; filename="review_labels_{library_id}.{format}"'}
    if format == "json":
        return JSONResponse(rows, headers=disposition)
    if format != "csv":
        raise HTTPException(400, "format must be json or csv")
    buf = io.StringIO()
    cols = [c for c in (rows[0] if rows else ["photo_id", "rel_path", "verdict", "reasons", "note"]) if c != "auto_snapshot"]
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({**r, "reasons": ";".join(r["reasons"])})
    # BOM so Excel opens Hebrew paths correctly.
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers=disposition)


# ------------------------------------------------------- quick labeling (ADR-022)
# The owner's album preference on a fixed seed sample. Blind: no scores, flags or AI suggestions are
# returned here. Stored in curation_labels, which the filter never reads (filtered/kept unchanged).
_seed_lock = threading.Lock()  # the sample file is rewritten when the owner nominates a photo
NO_SAMPLE = "אין עדיין מדגם לתיוג בספרייה הזו. לחצו על \"צור מדגם\" (או הריצו evaluation/make_seed_sample.py)."


def _sample_file(request: Request, library_id: int) -> Path:
    return seed_sample.sample_path(request.app.state.settings.data_dir, library_id)


def _load_sample_or_404(request: Request, library_id: int) -> dict:
    sample = seed_sample.load_sample(_sample_file(request, library_id))
    if sample is None:
        raise HTTPException(404, NO_SAMPLE)
    return sample


def _seed_state(request: Request, library_id: int, sample: dict, index: int | None, after: int | None = None) -> dict:
    repo = _repo(request)
    queue = []
    missing = 0
    for it in sample["items"]:
        if it["stratum"] not in seed_sample.LABELED_STRATA:
            continue
        photo = repo.find_photo_by_content(library_id, it["content_hash"], it.get("photo_id"))
        if photo is None or not seed_sample.original_exists(photo):
            missing += 1  # removed/moved since sampling (or since the last scan): can't be shown, skipped
            continue
        queue.append({**it, "photo_id": photo["id"], "_photo": photo})
    labels = repo.curation_labels_for(it["content_hash"] for it in queue)
    progress = repo.seed_progress(queue)
    dup_groups = {it["group_id"] for it in sample["items"] if it["stratum"] == "dup_groups"}
    picks = repo.get_duplicate_picks()
    picked = {it["group_id"] for it in sample["items"] if it["stratum"] == "dup_groups" and it["content_hash"] in picks}
    progress.update({"missing": missing, "dup_groups": len(dup_groups), "dup_groups_picked": len(picked & dup_groups),
                     "shortfall": sample.get("shortfall", {})})
    if index is None:
        # The next unlabeled item after `after` (skipped items are left for later), else the first unlabeled.
        unlabeled = [i for i, it in enumerate(queue) if it["content_hash"] not in labels]
        index = next((i for i in unlabeled if after is None or i > after), unlabeled[0] if unlabeled else None)
    elif queue:
        index = max(0, min(index, len(queue) - 1))
    else:
        index = None
    item = None
    if index is not None:
        it = queue[index]
        photo = it["_photo"]
        v = _media_version(photo)
        item = {"index": index, "photo_id": photo["id"], "stratum": it["stratum"],
                "preview_url": f"/api/photos/{photo['id']}/preview?v={v}",
                "label": labels.get(it["content_hash"])}
    return {"library_id": library_id, "progress": progress, "done": progress["labeled"] >= progress["total"],
            "item": item}


@router.get("/libraries/{library_id}/seed")
def get_seed(library_id: int, request: Request, index: int | None = Query(None, ge=0),
             after: int | None = Query(None, ge=-1)) -> dict:
    """The next unlabeled seed item (after position `after`, if given), or the one at `index` + progress."""
    _get_library_or_404(request, library_id)
    return _seed_state(request, library_id, _load_sample_or_404(request, library_id), index, after)


@router.post("/libraries/{library_id}/seed", status_code=201)
def create_seed(library_id: int, request: Request, replace: bool = False) -> dict:
    """Create the library's seed sample (deterministic). An existing one is replaced only with
    `replace=true` (e.g. the folder changed); it is kept as a .bak file, and labels are never deleted."""
    _get_library_or_404(request, library_id)
    _no_scan_running(request, library_id)
    path = _sample_file(request, library_id)
    with _seed_lock:
        if path.exists() and not replace:
            raise HTTPException(409, "A seed sample already exists for this library")
        sample = seed_sample.build_sample(_repo(request), library_id)
        if not sample["items"]:
            raise HTTPException(400, "לא נמצאו בספרייה תמונות שאפשר להציג. סרקו את התיקייה מחדש ונסו שוב.")
        if path.exists():
            path.replace(path.with_suffix(".bak"))
        seed_sample.save_sample(path, sample)
    return {"counts": sample["counts"], "shortfall": sample["shortfall"],
            **_seed_state(request, library_id, sample, None)}


class CurationIn(BaseModel):
    worthiness: str
    special: bool = False
    stratum: str | None = None


@router.put("/photos/{photo_id}/curation")
def set_curation(photo_id: int, body: CurationIn, request: Request) -> dict:
    """The owner's album preference for a photo (must / maybe / no + special). Never changes the filter."""
    p = _get_photo_or_404(request, photo_id)
    if p["status"] != "ok" or not p.get("content_hash"):
        raise HTTPException(400, "Only analyzed photos can be labeled")
    if body.worthiness not in CURATION_WORTHINESS:
        raise HTTPException(400, f"worthiness must be one of: {', '.join(CURATION_WORTHINESS)}")
    stratum = body.stratum
    if stratum is None:
        sample = seed_sample.load_sample(_sample_file(request, p["library_id"]))
        stratum = next((it["stratum"] for it in (sample or {}).get("items", [])
                        if it["content_hash"] == p["content_hash"]), None)
    return _repo(request).set_curation_label(p, body.worthiness, body.special, stratum,
                                             seed_sample.is_held_out(p["content_hash"]))


@router.delete("/photos/{photo_id}/curation")
def delete_curation(photo_id: int, request: Request) -> dict:
    p = _get_photo_or_404(request, photo_id)
    return {"deleted": _repo(request).delete_curation_label(p.get("content_hash"))}


@router.post("/photos/{photo_id}/nominate")
def nominate_photo(photo_id: int, request: Request) -> dict:
    """"★ חשובה": add this photo to the library's seed sample (stratum `nominated`)."""
    p = _get_photo_or_404(request, photo_id)
    if p["status"] != "ok" or not p.get("content_hash"):
        raise HTTPException(400, "Only analyzed photos can be nominated")
    path = _sample_file(request, p["library_id"])
    with _seed_lock:
        sample = _load_sample_or_404(request, p["library_id"])
        added = seed_sample.nominate(sample, p)
        if added:
            seed_sample.save_sample(path, sample)
    return {"added": added}


@router.get("/libraries/{library_id}/curation/export")
def export_curation(library_id: int, request: Request):
    """CSV of the owner's curation labels in this library (for the Curation Lead's metrics)."""
    _get_library_or_404(request, library_id)
    rows = _repo(request).export_curation_labels(library_id)
    cols = ["photo_id", "rel_path", "content_hash", "capture_time", "worthiness", "special", "stratum", "held_out",
            "blind", "source", "filtered", "filter_reason", "is_blurry", "is_screenshot", "exposure_issue",
            "quality_score", "created_at", "updated_at"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    disposition = {"Content-Disposition": f'attachment; filename="curation_labels_{library_id}.csv"'}
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers=disposition)


@router.get("/photos/{photo_id}/thumbnail")
def photo_thumbnail(photo_id: int, request: Request, v: str | None = None):
    p = _get_photo_or_404(request, photo_id)
    if not p.get("thumbnail_path"):
        raise HTTPException(404, "No thumbnail")
    path = request.app.state.settings.thumbnails_dir / p["thumbnail_path"]
    if not path.is_file():
        raise HTTPException(404, "Thumbnail file missing (rescan to regenerate)")
    return FileResponse(path, media_type="image/jpeg", headers=_media_headers(p, v))


@router.get("/photos/{photo_id}/preview")
def photo_preview(photo_id: int, request: Request, v: str | None = None):
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
    return Response(buf.getvalue(), media_type="image/jpeg", headers=_media_headers(p, v))


# Formats every browser can display as-is; others (HEIC) are converted for viewing.
_BROWSER_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


@router.get("/photos/{photo_id}/original")
def photo_original(photo_id: int, request: Request, v: str | None = None):
    """The original at full resolution, for judging sharpness at 100% (read-only)."""
    p = _get_photo_or_404(request, photo_id)
    src = Path(p["source_path"])
    if p["status"] != "ok" or not src.is_file():
        raise HTTPException(404, "Original not available")
    if p.get("format") in _BROWSER_FORMATS and p.get("mime_type"):
        return FileResponse(src, media_type=p["mime_type"], headers=_media_headers(p, v))
    try:
        with Image.open(src) as im:
            im.load()
            img = to_rgb(ImageOps.exif_transpose(im) or im)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=95)
    except Exception as exc:
        raise HTTPException(500, f"Cannot render original: {type(exc).__name__}") from exc
    return Response(buf.getvalue(), media_type="image/jpeg", headers=_media_headers(p, v))


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
