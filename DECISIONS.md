# Architecture Decision Log

Use this file for decisions that would otherwise be forgotten.

## ADR-001 — Local-first MVP
**Status:** Accepted

**Decision:** The first MVP processes local folders and stores derived metadata locally.

**Why:** Faster experimentation, lower privacy risk, avoids cloud cost before product validation.

**Consequence:** Native mobile gallery integration and scalable cloud jobs are deferred.

## ADR-002 — Provider abstractions for AI
**Status:** Accepted

**Decision:** Face recognition, semantic embeddings, aesthetic scoring and rendering are accessed through interfaces/adapters.

**Why:** Licensing, model quality, hardware and cost may change.

**Consequence:** Slightly more architecture upfront, much easier replacement later.

## ADR-003 — Derived data lives outside the project folder and outside cloud-synced folders
**Status:** Accepted (2026-09-26)

**Decision:** SQLite DB, thumbnails and logs default to `~/.ai-photo-album/data` (configurable via `APP_DATA_DIR`). The Python venv lives in `~/.ai-photo-album/venv`.

**Why:** The project folder is inside OneDrive. Thumbnails of personal photos syncing to the cloud would violate the privacy principle; SQLite on a syncing folder risks lock/corruption; a venv on OneDrive syncs thousands of files. (Also: the Claude desktop app redirects `%LOCALAPPDATA%` for its own processes, so the user-profile root is used so the app and the developer tooling see the same data.)

**Tradeoff:** Data is not next to the project. **Changeable:** yes, one setting.

## ADR-004 — Plain `sqlite3` with a repository layer (no ORM yet)
**Status:** Accepted (2026-09-26)

**Decision:** All SQL lives in `app/db/` (`database.py` schema, `repository.py` queries). Business logic never writes SQL. Short-lived connections + WAL mode.

**Why:** Zero extra dependencies, fast, transparent, easy to test. **Tradeoff:** moving to Postgres later means rewriting the repository (not the pipeline). Schema versioning is a simple `meta.schema_version`; add real migrations (e.g. Alembic) when the schema starts changing on user machines.

## ADR-005 — Duplicate detection = exact SHA-256 + near-duplicate pHash AND dHash
**Status:** Accepted (2026-09-26)

**Decision:** Exact duplicates share a SHA-256. Near duplicates need pHash Hamming ≤ 8 **and** dHash Hamming ≤ 12 (both configurable). Groups are connected components; one "best" photo per group (highest technical quality, then resolution). Nothing is deleted — alternates are only de-prioritized and remain available to the user.

**Why:** Deterministic, license-free, explainable. Requiring two hashes lowers false positives. Comparison is vectorized (numpy popcount): O(n²) but ~seconds for 20k photos.

**Tradeoff:** Hashes miss "same moment, different framing" bursts; Milestone 2 embeddings will add semantic near-duplicate detection. For >100k photos switch to a BK-tree/multi-index hashing.

## ADR-006 — Technical quality via transparent classical metrics
**Status:** Accepted (2026-09-26)

**Decision:** Sharpness = 90th percentile of per-tile Laplacian variance (4×4 tiles, image normalized to 1024px, luminance contrast-stretched to its 1st–99th percentiles first so dark-but-sharp photos are not flagged as blurry — found during M1 verification). Exposure = luminance mean + clipped fractions. `quality_score` = 0.5·sharpness + 0.2·exposure + 0.1·contrast + 0.2·resolution, with components exposed.

**Why:** Tile-based sharpness does not penalize shallow depth-of-field portraits (sharp subject, blurred background). Transparent components support the "explainable score" requirement.

**Tradeoff:** Thresholds are heuristics; they must be calibrated with the evaluation harness on real libraries. Blurry/low-quality photos are **flagged, not discarded** (meaningful moments may be imperfect).

## ADR-007 — Capture time resolution order: EXIF → filename → file mtime
**Status:** Accepted (2026-09-26)

**Decision:** `DateTimeOriginal`/`DateTimeDigitized`/`DateTime` from EXIF; else a date parsed from the filename (`IMG_20190512_…`, WhatsApp `IMG-20190512-WA…`, Pixel `PXL_…`); else the file modification time. The source is stored (`capture_time_source`) so later stages can treat `file_mtime` dates as unreliable.

**Why:** WhatsApp/messaging exports usually strip EXIF but keep the date in the filename; mtime is often the copy date.

## ADR-008 — Ingestion runs as a background job with a process pool
**Status:** Accepted (2026-09-26)

**Decision:** A single background thread runs the pipeline; per-file analysis (hash, decode, thumbnail, quality) runs in a `ProcessPoolExecutor` (CPU count − 1, max 8). Job progress is persisted in SQLite and polled by the UI. Rescans are incremental (size + mtime). Missing files are marked `missing`, never deleted.

**Why:** Decoding is CPU-bound; processes bypass the GIL. JPEG `draft` mode decodes at reduced scale (large speedup). **Tradeoff:** one job at a time. A real queue (e.g. RQ/Celery or native OS background tasks) can replace `JobManager` without changing the API.

## ADR-009 — Local server hardening
**Status:** Accepted (2026-09-26)

**Decision:** Bind to `127.0.0.1` only; `TrustedHostMiddleware` rejects foreign Host headers (DNS-rebinding protection). The API only serves files that are indexed photos or generated thumbnails.

## ADR-010 — MVP UI: static HTML/JS served by FastAPI, Hebrew RTL
**Status:** Accepted (2026-09-26)

**Decision:** The local UI is plain HTML/CSS/vanilla JS in `app/web/static/` (no build step, no framework), Hebrew right-to-left. Folder selection uses a native OS dialog launched by the local server (`POST /api/system/pick-folder`, tkinter subprocess) plus a manual path field.

**Why:** Zero tooling for a non-programmer owner; enough for inspection/review screens. **Tradeoff:** the future visual album editor (M6/M8) will likely need a component framework; the JSON API is the stable contract, so the UI can be replaced without backend changes. UI strings are inline Hebrew — i18n needed before a multi-language release.

## ADR-012 — IDs are never reused; image URLs are content-versioned
**Status:** Accepted (2026-09-26) — fixes a real Milestone 1 bug

**Bug:** Owner scanned folder A, deleted it, scanned folder B (one photo): the UI showed A's photo. The database was correct. Cause: `libraries`/`photos`/`duplicate_groups` used plain `INTEGER PRIMARY KEY`, which SQLite reuses (max(id)+1) after deletes, so B's photo got A's old ID → identical URL `/api/photos/1/thumbnail`, which was served with `Cache-Control: max-age=86400` → the browser displayed its cached copy of A. Same failure when a file is replaced in place with new content.

**Decision:**
1. Those three tables use `INTEGER PRIMARY KEY AUTOINCREMENT` (schema v2): a deleted ID is never handed out again. This also protects future references to photo IDs (human labels, album projects). Existing v1 databases are migrated automatically on startup (create-copy-drop-rename; IDs preserved; FK check).
2. Image URLs carry `?v=<first 16 hex of SHA-256>`. Only a request whose `v` matches the photo's current content hash is cached (`immutable`); unversioned/outdated URLs get `no-cache`; every response has `ETag` = content hash.
3. All `/api/` JSON responses are `no-store`.

**Rule for future work:** any URL for derived media (thumbnails, previews, crops, rendered pages) must include a content/version component; never cache a URL whose meaning can change.

**Tradeoff:** AUTOINCREMENT is marginally slower on insert (negligible here).

## ADR-013 — Single-instance server: bind first, refuse to hide behind an outdated copy
**Status:** Accepted (2026-09-26) — second part of the "folder B shows folder A's photo" bug

**What happened:** after ADR-012 was implemented, the owner re-ran `start.bat` while the pre-fix server (started 13:38:48) was still running. The launcher opened the browser unconditionally; the new process ran `create_app` (DB migrated to v2, "app started" logged at 13:56:31), then failed to bind port 8765 and exited. The browser therefore kept talking to the OLD process, which still issued ID-only URLs (`/api/photos/2/thumbnail`, `max-age=86400`) — photo ID 2 had belonged to an earlier scanned folder, so the browser showed its cached copy. The DB, the source file (SHA-256 `f10ef91f…`) and the generated thumbnail were all correct.

**Decision:**
1. `python -m app serve` binds the port **before** creating the app (exclusive bind on Windows via `SO_EXCLUSIVEADDRUSE`) and hands the socket to uvicorn. A process that cannot serve does no DB work.
2. If the port is taken, `/api/health` of the existing server is probed. Same `build` → "already running", open browser. Different/older build (pre-ADR-013 copies report no build) → clear error, exit code 4, browser NOT opened. Other program → exit code 3.
3. The browser is opened by the server itself (`--open-browser`), only after it is actually serving. `start.ps1` no longer opens it.
4. `/api/health` reports `app`, `build` (fingerprint of the running code) and `pid`; the UI header shows the build; startup log includes build + pid.
5. `index.html`/`app.js` are served `no-cache` so a code update is always picked up.

**Tradeoff:** an outdated copy is not killed automatically (the owner closes its window) — explicit and predictable over magical. **Changeable:** could later auto-stop the old copy using the reported pid.

## ADR-014 — In-app folder browser for choosing a photo folder
**Status:** Accepted (2026-09-26) — UX task, not part of Milestone 2

**Problem:** the native Windows "choose folder" dialog shows folders only, so the owner cannot see the photos inside a folder before choosing it.

**Options considered:** (a) native "open file" dialog and take the file's folder — awkward, cannot force thumbnail view; (b) browser `showDirectoryPicker`/`webkitdirectory` — the browser never reveals the real path and would require uploading the files; (c) desktop shell (Electron/pywebview) — heavy and still uses the same native dialog; (d) **chosen:** a read-only folder browser inside the web UI.

**Decision:** `app/services/folder_browser.py` + `app/api/browse.py` (`GET /api/browse/roots`, `GET /api/browse?path=&offset=&limit=`, `GET /api/browse/thumbnail?path=&v=`). The UI dialog lists quick-access places + drives, subfolders, and a lazily loaded grid of image thumbnails and video tiles (pages of 200, thumbnails requested only near the viewport). "Choose this folder" fills the path field; the native dialog and manual field remain as fallbacks.

**Safety rules:**
1. Only absolute paths on allowed roots (local fixed/removable drives; configurable `APP_BROWSE_ROOTS`). UNC/network, device paths (`\\?\`, `\\.\`), NTFS alternate data streams, NUL are rejected before touching the disk; the *resolved* path (after symlinks/junctions) must still be inside a root.
2. Non-media files are skipped by extension without stat/open; videos are only listed (size), never opened; only images are decoded, read-only, into an in-memory 256px JPEG. Nothing is written to disk or to the database.
3. OneDrive online-only placeholders (`RECALL_ON_DATA_ACCESS`/`RECALL_ON_OPEN`/`OFFLINE` attributes) are shown as cloud tiles and never opened, so browsing never triggers a download.
4. Requests with `Sec-Fetch-Site` other than `same-origin`/`none` are refused, so another website open in the browser cannot probe local files via `<img>` tags.
5. Thumbnail URLs are versioned by size+mtime (ADR-012).

**Tradeoffs:** thumbnails are rendered on the fly (~20 ms per 12 MP JPEG; HEIC slower) instead of using the Windows thumbnail cache; network drives are not browsable (manual path still works); the scanner itself still indexes images only and still reads cloud-only files when scanning (existing M1 behaviour — the browser shows how many files are cloud-only). **Changeable:** yes, UI-only feature behind a small API.

## ADR-015 — Page/asset versioning by build + "new version" banner
**Status:** Accepted (2026-09-26)

**What happened:** after the folder browser was added, the owner saw the new "עיון בתיקיות…" button but clicking it did nothing. Cause: `app.js` had been served (before ADR-013) without any Cache-Control, so Chrome cached it heuristically; a normal refresh reloaded the page (new button) but reused the old cached script (no click handler).

**Decision:**
1. `index.html` is rendered with the build id: `/static/app.js?v=<build>`, `/static/styles.css?v=<build>` and `<meta name="app-build">`. A new build always means new asset URLs, so a page and its script can never come from different builds.
2. The page compares its build with `/api/health` on load, every 30 s, and when the tab regains focus; if they differ it shows a banner "יש גרסה חדשה של האפליקציה" with a reload button.

**Tradeoff:** one health request every 30 s (local, negligible). **Changeable:** yes.

## ADR-011 — Synthetic fixtures instead of real photos in tests
**Status:** Accepted (2026-09-26)

**Decision:** Tests generate their own photos (`tests/fixtures.py`: textured scenes with EXIF dates, GPS, orientation, copies, resized near-duplicates, blur, darkness, screenshot size, truncated file). `scripts/make_sample_library.py` builds large synthetic libraries for benchmarks.

**Why:** No personal data in the repo; deterministic tests. **Tradeoff:** synthetic images don't reflect real-photo statistics — real-library evaluation is still required.
