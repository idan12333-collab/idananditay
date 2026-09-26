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

## ADR-017 — Print-aware resolution instead of a megapixel cutoff
**Status:** Accepted (2026-09-26) · supersedes the resolution part of ADR-006 · schema v4

**What happened:** M1 flagged every photo under 1.0 MP as "low resolution" (`is_low_res`) and made resolution 20% of the technical `quality_score` (`sqrt(MP/8)`). Both numbers were placeholders, not print math. On the owner's library the 51 flagged files really were 160×120 / 160×90 thumbnail-sized copies, but the rule would also flag e.g. 1024×768, which prints well at ~13×10 cm, and the score penalty ranked sharp 2 MP photos below mediocre 12 MP ones.

**Decision:**
1. Store only native pixel dimensions (already stored, EXIF-oriented). Print suitability is *derived*: `app/printing/suitability.py` computes effective PPI = min(long px / slot long in, short px / slot short in) for a photo filling a slot (excess cropped, slot rotated to match the photo).
2. Levels (configurable starting defaults, to be overridden by the chosen print provider's spec): ≥300 excellent, ≥200 good, ≥150 acceptable, below = "not recommended at this size". Reference slots 6×9, 10×15, 13×18, 15×20, 20×30, 30×30 cm (`APP_PRINT_*`).
3. The only strong warning is "extremely low resolution": cannot reach acceptable PPI even in the smallest slot (`APP_PRINT_MIN_SLOT_CM`, default 6×9 cm → needs ≥532×355 px). The smallest slot is a setting, not a product rule — future layouts may have smaller slots. Computed in SQL from width/height, so changing the setting needs no rescan.
4. Resolution is removed from `quality_score` (now 0.625·sharpness + 0.25·exposure + 0.125·contrast, same proportions as before). Resolution never excludes a photo; the final check is per slot at layout/export time (with the user's crop).
5. Duplicate "best": among members within 0.05 quality of the top, the one with the most pixels wins (an original beats its compressed copy).
6. Migration v4: drops `photos.is_low_res`, recomputes `quality_score` from stored measurements, and the app refreshes duplicate groups once after migrating. No image is re-read.

**Tradeoff:** a per-size table is more to show than one flag; the PPI levels are industry rules of thumb until a provider is chosen. **Changeable:** yes — all numbers are settings; the policy is one small pure module.

**Revision (2026-09-26, owner direction):** print suitability is **internal only**. Customers never see print sizes, PPI or "fits up to 20×30" — size handling must be automatic and invisible (the future layout engine uses `app/printing/suitability.py` to place each photo in a slot it can fill). In the UI a photo that cannot fill even the smallest slot is simply filtered as "איכות נמוכה מדי". The per-size table stays available to developers only (viewer "פרטים טכניים", shown with `?debug` in the URL).

## ADR-018 — Human review labels, stored apart from automatic analysis
**Status:** Accepted (2026-09-26) · schema v4

**Decision:**
1. A full-screen review viewer (click any photo): large image, 100% zoom from the original (`/api/photos/{id}/original`, read-only; HEIC converted for viewing), every automatic measurement next to the rule that produced its flag, print suitability per size, file facts (incl. extension ≠ real format), duplicate group.
2. Labels: "looks good" / "bad / unsuitable" + optional reason tags (blurry, exposure, low_res, screenshot, duplicate, not_a_photo, other) + note. Keyboard: 1 / 2 / 0 (clear), ←/→, Z.
3. Stored in `review_labels`, keyed by `content_hash` (survives rescans; identical copies share a label; counted once in evaluation). A label never writes to `photos`. Each label keeps a JSON snapshot of the automatic verdicts shown at labeling time, so later threshold changes do not lose what the reviewer was judging.
4. Evaluation: filters (unreviewed / good / bad / "automatic analysis and human disagree"), per-flag agreement (flag precision, false alarms, misses by reason tag), JSON/CSV export. Current flags are classical rules, not AI — named accordingly in the UI.
5. Deleting a library index also deletes labels no remaining photo refers to (privacy: derived personal data is deletable).

**Tradeoff:** labels keyed by content mean an edited file (new bytes) is unreviewed again — acceptable, it is a different image. **Changeable:** yes.

**Revision (2026-09-26, after the owner's first manual test — the first viewer was "too complicated"):**
6. The main review flow is **"מה הסינון עשה?"**: a summary ("מתוך 97 תמונות: X נשארו · Y סוננו"), one clickable tab per filter reason (blurry, too dark/bright, duplicates, screenshots, too small to print) plus "נשארו" and "הטעויות שסימנת", and a grid of large thumbnails with one-tap corrections: "↩ הסינון טעה — החזר" on a filtered photo (= label good) and "✗ היה צריך לסנן" on a kept one (= label bad), each undoable. A feedback line counts the corrections.
7. **Nothing is lost:** duplicates are now a filter reason like the others, and the filter's *effective* decision is: human label if any, otherwise the automatic reasons (`filtered` / `kept` filters, COALESCE-safe SQL). Automatic results stay unchanged underneath (`auto_filtered` / `auto_kept`).
8. **Duplicate keeper choice:** groups are shown side by side with ⭐ on the kept photo; "שמור את זו במקום" stores the user's pick in `duplicate_picks` (keyed by content hash, so it survives the regrouping every scan does); `duplicate_groups.auto_best_photo_id` keeps the automatic choice for display and for counting changed picks; "חזרה לבחירה האוטומטית" removes the pick; "שמור גם את זו" keeps an alternate too (label good). Byte-identical copies show "עותק זהה" — there is nothing to choose. Both additions are additive and idempotent within schema v4 (the owner's DB was already v4).
9. The single-photo viewer is secondary (opened from any thumbnail): the photo always fills the stage (small photos enlarged and drawn pixelated, with a note saying so), ONE plain Hebrew traffic-light verdict (print suitability; when the filter removed the photo, the box turns amber and says why), a print-size picker (10×15 / 15×20 / 20×30 / full page) that shows a 6×6 cm patch of that print at 300 PPI-equivalent, two big 👍/👎 buttons (1/2), reason chips (max 4) only after 👎, note behind a link, and every measurement in a collapsed "פרטים טכניים".
10. Agreement stats and JSON/CSV export moved to a collapsed "נתונים לכיול הסינון (מתקדם)".

**Scope of the filter (owner, 2026-09-26 — supersedes an earlier "people and animals = memories" framing):** the rule-based filter makes only **technical/format** judgments — duplicate copies, image quality (blur, too small), exposure, screenshot format. It never decides what is relevant: landscapes, objects or even screenshots may belong in an album depending on the request. Relevance ("what belongs in *this* album") is decided later by the album request plus semantic/people signals (M2+, after a license check and the owner's approval). Wording is therefore neutral: "הסינון הציע להוציא" / "פחות מתאימה כרגע לאלבום" + the technical reason; kept = "נשארה בבחירה"; the user's buttons are "↩ להחזיר לבחירה" / "✗ להוציא מהבחירה".

**Effective decision rule (fix after owner test #3 — restoring a photo leaked extra duplicate copies into "kept"):**
- *Duplicates are resolved independently of labels:* in every duplicate group exactly one copy stays — the automatic choice or the user's pick ("שמור את זו במקום"). A label on a non-kept copy never keeps it; "keep this one too" was removed.
- *Technical reasons* (screenshot, low quality, exposure): a "good" label overrides all of them; a "bad" label removes the photo even without a reason. Undo = delete the label → exactly the previous state.
- *One photo = one place:* kept and filtered partition all photos; each filtered photo has ONE primary reason and appears in one tab only, priority עותק כפול > צילום מסך > איכות ירודה (blur + too small, merged for customers, separate internally) > תאורה (חשוכה / בהירה מדי) > "הוצאת ידנית"; other reasons show as small text on the tile. Counts add up (kept + filtered = total; tabs = filtered). Server: `_FILTERED`, `_PRIMARY`, filters `reason_*`, `changes`; tests assert all of this.
- *Screenshot rule unchanged:* the photos the owner restored from "צילומי מסך" were real screenshots (status bar visible) *of* people — a relevance judgment, correctly handled by restoring, not a format error.
11. The viewer's verdict box shows only the filter decision in neutral words ("✅ נשארה בבחירה" / "הסינון הציע להוציא — …" + technical reason / "↩ החזרת אותה לבחירה"); the print-size picker/simulation was removed from the customer UI.

## ADR-019 — Local project-management dashboard (dev tooling)

**Status:** accepted (2026-09-26, owner approved via PM).

**Context.** Several Claude sessions (PM + workers) work in parallel on one working
tree. The owner is non-technical and needs a quick, trustworthy view of the state
without reading markdown files or chat transcripts.

**Decision.** A separate, stdlib-only local web dashboard in `project_management/`,
served on `127.0.0.1:8790` by `start_project_manager.bat`. It aggregates git (read-only
allowlist), the coordination docs, a PM-written `state.json` (git-ignored), PM-written
daily summaries (committed) and, optionally, Claude Code transcripts (read-only,
redacted, estimate-only context). Actions are honest *requests* appended to
`inbox.jsonl` for the owner to paste to the PM; the dashboard never controls sessions.

**Tradeoffs.** The PM must keep `state.json` current (the dashboard is only as fresh as
it is). The transcript format is undocumented, so that adapter is isolated in one
module and degrades to "no data". Hebrew-only UI.

**Reversible?** Yes — delete `project_management/` and the `.bat`; the product is untouched.

## ADR-020 — Dev-mode auto-reload supervisor (dev tooling)

**Status:** accepted (2026-09-26, owner approved via PM).

**Context.** During development every code change required the owner to close the CMD
window and restart the app/dashboard, and a forgotten old process could keep serving stale
code (the ADR-012/013 incident).

**Decision.** `start_dev.bat` runs `scripts/dev_supervisor.py` (stdlib only), which starts the
album app and the dashboard as child processes and polls file mtimes every 0.5 s — only
`.py/.html/.js/.css` under `app/` and `project_management/` (never tests, `__pycache__`, `.git`,
editor/OneDrive temp names, or the data in `~/.ai-photo-album`). A burst of changes is debounced
(1 s of quiet) into one restart of the affected server: kill the whole process tree (the venv
`python.exe` is a launcher whose real interpreter is a grandchild) → verify it exited and the
port is free → start the new child → verify `/api/health` echoes a fresh per-start token
(`dev_instance`). Any failure is reported loudly and nothing stale is left serving. In dev mode
only (`AI_ALBUM_DEV_RELOAD=1`), the app page (a `<meta>` injected by `main.py`) and the dashboard
page (`dev_reload` in its new `/api/health`) poll every 2 s and reload on a new build. Servers are
killed, not shut down gracefully, so a scan cannot write "done": it stays `running` and the next
start marks it `interrupted` (existing JobManager behaviour; regression-tested).

**Tradeoffs.** Polling instead of OS file events (no new dependency; negligible cost on these
small trees). Any code save restarts the server and cancels a running scan (dev only).
`start.bat` / `start_project_manager.bat` are unchanged.

**Reversible?** Yes — delete `start_dev.bat` and `scripts/dev_supervisor.py`; the hooks are inert
without the env vars.
