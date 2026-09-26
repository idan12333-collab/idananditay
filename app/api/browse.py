"""Folder-browser API for the "choose a photo folder" dialog (read-only; ADR-014)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import folder_browser as fb

IMMUTABLE_CACHE = "private, max-age=31536000, immutable"


def same_origin_only(request: Request) -> None:
    """Blocks other websites open in the browser from probing local files through this API.

    Browsers send ``Sec-Fetch-Site`` on every request (including <img>); only our own page
    (``same-origin``) or direct navigation (``none``) is allowed. Clients that send no such
    header (tests, curl) are local processes and are allowed.
    """
    site = request.headers.get("sec-fetch-site")
    if site is not None and site not in ("same-origin", "none"):
        raise HTTPException(403, "Cross-site request refused")


router = APIRouter(prefix="/api/browse", dependencies=[Depends(same_origin_only)])


def _roots(request: Request):
    return fb.allowed_roots(request.app.state.settings.browse_roots)


def _fail(exc: fb.BrowseError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


@router.get("/roots")
def browse_roots(request: Request) -> dict:
    return {"locations": fb.shortcuts(_roots(request))}


@router.get("")
def browse_folder(
    request: Request, path: str, offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=fb.MAX_PAGE)
) -> dict:
    try:
        listing = fb.list_folder(path, _roots(request), offset, limit)
    except fb.BrowseError as exc:
        raise _fail(exc) from exc
    listing["items"] = [
        {
            "name": m.name,
            "path": m.path,  # used by the UI to mark files to exclude from the scan (ADR-016)
            "kind": m.kind,
            "size": m.size,
            "cloud_only": m.cloud_only,
            # Versioned by size+mtime (ADR-012): a changed file gets a new URL.
            "thumbnail_url": (
                f"/api/browse/thumbnail?path={quote(m.path, safe='')}&v={m.version}"
                if m.kind == "image" and not m.cloud_only
                else None
            ),
        }
        for m in listing["items"]
    ]
    return listing


@router.get("/thumbnail")
def browse_thumbnail(request: Request, path: str, v: str | None = None):
    try:
        data, version = fb.render_thumbnail(path, _roots(request))
    except fb.BrowseError as exc:
        raise _fail(exc) from exc
    cache = IMMUTABLE_CACHE if v == version else "no-cache"
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": cache, "ETag": f'"{version}"'})


class SummaryRequest(BaseModel):
    path: str
    exclude: list[str] = []


@router.post("/summary")
def browse_summary(body: SummaryRequest, request: Request) -> dict:
    """Recursive counts before scanning: found / excluded / will be scanned (ADR-016)."""
    try:
        return fb.summarize_folder(body.path, _roots(request), body.exclude)
    except fb.BrowseError as exc:
        raise _fail(exc) from exc
