# Project Memory

This file is Claude Code's durable project memory. Keep it short and factual. Update it after meaningful decisions or milestones.

## Product
We are building a general-purpose AI photo curator + album generator. It is not limited to travel. A user may request an album about a person across many years, a relationship, a trip, birthdays, a year, or another theme.

## Core differentiator
The system searches and curates a large photo library automatically before laying out the album.

## Current phase
Milestones 0–1 complete and closed (2026-09-26). Milestone 2 NOT started (owner asked to wait).

## Current state (session handoff)
- Code state: all code saved; 89/89 tests passing (last run 2026-09-26).
- **Filter scope (owner, 2026-09-26):** the filter makes only technical/format judgments (duplicates, quality, exposure, screenshot format); relevance comes later from the album request + M2 signals. Neutral wording only (no "memory" language). Customers never see print sizes (ADR-017 revision). Duplicates: exactly one kept copy per group, independent of labels (ADR-018).
- Delete-library stale-UI bug fixed (resetLibraryUI + orphan-thumbnail sweep on delete). Owner's 19 "error" files are non-images with photo extensions (8 videos, 5 AAE/XML sidecars, 7 empty files) and the 51 tiny files are tiny on disk — both come from the owner's export, not from our ingest.
- 2026-09-26: owner REJECTED the first review viewer (too technical, tiny image). Reworked per owner/PM: main flow = "מה הסינון עשה?" batch review; duplicates = a filter reason; `duplicate_picks` table + `duplicate_groups.auto_best_photo_id` (additive, idempotent, still schema v4); simplified viewer. See ADR-018 revision. Awaiting the owner's second manual test; NOT committed.
- Coordination: PM session ("project manager") + ACTIVE_WORK.md board. Commit split for W1 (this work) is scripted/verified via a temporary worktree; the W1-only versions of database.py/repository.py are produced by removing W2's exclusion hunks. Re-verify (stash --keep-index) right before committing.
- Real-library findings: MROC7762.JPG etc. are 160px copies stored sideways with EXIF orientation=1 (not our bug); the library has 0 blur flags but IMG_1160.JPG is a clearly out-of-focus close-up (sharpness 93 > threshold 40) → blur threshold too low / metric weak; white screenshots get flagged "overexposed". Calibration input for later.
- **In progress / uncommitted (2026-09-26):** print-aware resolution (ADR-017) + full-screen review viewer & human labels (ADR-018), schema v4. Implemented and tested (incl. a dev run on a COPY of the owner's DB: migration v2→v4 OK, 51 extremely-low-res = the 160px thumbnail files, labeling/zoom/agreement verified in the browser). **Do NOT commit until the owner tests it manually**, and commit it separately from other work.
- **Parallel session:** another Claude session ("החרגת תמונות בסינון", library exclusions) edits the same working tree. Agreed split: it owns schema v3 = `library_exclusions` + ADR-016 (scanner.py, folder_browser.py, api/browse.py, exclusion code in repository/database, `IngestionPipeline.run` scan part, `LibraryCreate`/`create_library`, fb* UI + section-1 card). This work owns schema v4 + ADR-017/018. Shared files (database.py, repository.py, pipeline.py, routes.py, app.js, index.html, styles.css) contain hunks of both — stage per hunk when committing.
- Finding: classical sharpness is meaningless on tiny images (a 160×90 file scored sharpness 8219 → quality 100/100). The review labels will show this; consider a minimum analysis size in calibration.
- Git: bug fixes ADR-012/013 committed as `296d922`. The folder-browser UX (ADR-014: `app/services/folder_browser.py`, `app/api/browse.py`, `tests/test_folder_browser.py`, UI dialog in index.html/app.js/styles.css, `browse_roots` setting) plus the new-version banner / build-versioned assets (ADR-015, `app/main.py` index route) are committed separately (owner approved, 2026-09-26).
- 2026-09-26: fixed real-photo bug "folder B shows folder A's photo" (root cause: SQLite ID reuse after library delete + ID-only image URLs cached by the browser for 24h). Fix = schema v2 AUTOINCREMENT + content-versioned image URLs + no-store API JSON (ADR-012). Regression tests: `tests/test_library_isolation.py`. The owner's DB (`~/.ai-photo-album/data`) migrates to v2 automatically on next app start (verified on a copy).
- 2026-09-26 (later): owner reported the bug persisted. Real cause: the PRE-FIX server process (pid 6868, started 13:38:48) was still running; relaunching start.bat failed to bind the port silently while the launcher opened the browser anyway, so the old code kept serving. DB/source/thumbnail were verified correct (sha256 f10ef91f…, identical pHash). Fixed with a single-instance guard (ADR-013, `app/core/instance.py`, `tests/test_instance.py`). 40/40 tests pass.
- Owner must close the old app window once (old copies cannot be detected by build id; the new launcher now refuses to start and says so).
- Debug tip: `/api/health` shows `build` and `pid` of the process actually answering; the UI header shows the build.
- Last user instruction (2026-09-26): folder-browser/cache work committed separately (`7927635`); then implement print-aware resolution (300/200/150 PPI configurable defaults, configurable smallest slot, resolution out of quality score, never auto-exclude) + review viewer & separate labels ("Automatic analysis and human disagree" naming); do NOT commit until the owner tests manually; do NOT start M2.
- **Recommended next action:** when the owner approves M2 — (1) research + record license of candidate image-text embedding models in MODEL_REGISTRY.md (code AND weights, commercial use), (2) propose the choice to the owner, (3) only then implement `ImageEmbeddingProvider` + local `VectorStore`, (4) build a minimal evaluation harness (relevant/irrelevant labels, precision@K) alongside it.
- Useful before M2: owner runs the app on a copy of a real photo folder and reports mis-flags → calibrate blur/exposure/screenshot thresholds.

## Environment facts
- Windows 11, Python 3.12 (`py -3.12`). Venv: `%USERPROFILE%\.ai-photo-album\venv`. Data: `%USERPROFILE%\.ai-photo-album\data` (ADR-003).
- Project folder is inside OneDrive with a Hebrew path — keep derived data/venv out of it.
- Claude desktop app redirects `%LOCALAPPDATA%` for its own processes → never use LOCALAPPDATA for shared paths.
- Git for Windows installed; repo initialized 2026-09-26 on branch `main`, no remote. Author identity is set in the repo-local git config only.
- Run: `start.bat` (UI on http://127.0.0.1:8765), tests: `run_tests.bat` or `python -m pytest -p no:cacheprovider` (cache disabled because of OneDrive).
- `PRINT_INTEGRATION (1).md` is a byte-identical duplicate of `PRINT_INTEGRATION.md` (can be deleted by the owner).
- CLI: `python -m app serve` | `python -m app scan <folder>`. Synthetic test library: `python scripts/make_sample_library.py OUT --count N` (slow: ~1.5 s per 12 MP photo).
- For dev/verification runs use a separate data dir (`APP_DATA_DIR`, e.g. in the scratchpad) and `APP_PORT=8766` so the owner's real data at the default location is untouched.
- Tests emit one harmless warning: Starlette deprecates `httpx` for TestClient (suggests `httpx2`). Not yet addressed.

## Measured (synthetic 12 MP JPEGs, 8-core laptop, 7 workers)
- Full ingest: ~51 s per 1,000 photos. Incremental rescan of 1,000 unchanged: ~0.3 s.
- Detected all planted exact copies (32 groups) and bursts (73 groups), 17.9% duplicate reduction.
- Real-library calibration of blur/exposure thresholds is still pending (needs evaluation harness).
- Benchmark lesson: generating the 1,000 synthetic 12 MP photos took ~25 min vs. a 51 s scan. Reuse a persistent dataset (suggested: `%USERPROFILE%\.ai-photo-album\benchmarks\sample_1000`, generate only if missing) or a cheaper setup; don't regenerate large datasets unnecessarily. Details: README "Benchmarking". The M1 dataset lived in a session scratchpad and should be assumed gone.

## Current strategy
Build a local desktop/web proof of concept first. Do not start with native iOS.

## Key principles
- Local-first/privacy-first.
- Never modify originals.
- Use replaceable AI provider interfaces.
- Verify commercial licensing before production adoption.
- Person matching supports multiple reference images and uncertainty.
- Selection must balance beauty, relevance, diversity, chronology and event coverage.
- Human review is part of the product.
- Measure quality with an evaluation harness.

## Decisions
- Python + FastAPI + SQLite baseline.
- Album output should include editable project JSON plus PDF preview/export.
- Avoid a single monolithic AI model; use specialized components behind interfaces.
- Plain sqlite3 + repository layer (ADR-004); duplicates = SHA-256 + pHash∧dHash (ADR-005); classical tile-based quality (ADR-006); capture time EXIF→filename→mtime with source stored (ADR-007); background job + process pool (ADR-008); localhost-only + TrustedHost (ADR-009).
- Duplicates/blurry photos are flagged and de-prioritized, never deleted.
- pillow-heif binary wheels are GPLv2 → HEIC decoding is POC_ONLY (MODEL_REGISTRY).

## Open questions
- Final commercially licensed face model/provider.
- Final image-text embedding model.
- Final aesthetic scoring model.
- Best local vector index for MVP.
- Printing partner and print specifications.
- Native iOS architecture after MVP validation.

## Completed milestones
- M0 Foundation + M1 Photo ingestion (2026-09-26): config, logging, SQLite, ingestion pipeline, thumbnails, duplicates, quality signals, Hebrew RTL UI, CLI, 27 passing tests. Provider interfaces (embeddings/faces/aesthetics/captions/vector store/renderer/print provider) exist as abstract classes only.

## Known limitations / follow-ups
- Near-duplicate detection is hash-based: misses "same moment, different framing"; add embedding similarity in M2.
- O(n²) near-dup comparison is fine to ~20–30k photos; switch to BK-tree/multi-index beyond that.
- Screenshot detection is heuristic (filename / PNG at screen size without camera EXIF).
- No evaluation harness yet — required before tuning thresholds (plan it with M2).
- Quality thresholds only validated on synthetic images, not on a real library.
- Single background job at a time (JobManager); no job queue.
- Schema versioning: `meta.schema_version` = 2 with a hand-written v1→v2 migration in `app/db/database.py`; consider a real migration tool when schema changes become frequent.
- Rule (ADR-012): media URLs must be content-versioned; DB IDs are never reused.
- Rule (ADR-017): resolution is never a global good/bad flag and never excludes a photo; judge effective PPI per print size. Rule (ADR-018): human labels live in `review_labels` and never modify `photos`.
- Rule (ADR-015): index.html is served with `__BUILD__` replaced; static asset URLs must carry `?v=<build>`.
- Rule (ADR-014): the folder browser never opens non-image files and never opens OneDrive cloud-only placeholders; all browse paths must resolve inside the allowed roots.
- Rule (ADR-013): only one server per port; `serve` binds before doing any work; verify the running `build` when debugging "my fix didn't work".

## Open issues
1. HEIC decoding license (pillow-heif GPLv2 wheels) — must be resolved before any commercial distribution.
2. Threshold calibration on real photos pending — the review viewer (ADR-018) now provides the labels; owner needs to label a sample.
3. `Git-2.55.0.5-64-bit.exe` installer sits in the project folder (git-ignored); owner may delete it.


## Final product requirement
The product must ultimately be a complete consumer app, not just an AI selector. After curation it must automatically create a real page-by-page photo book, allow visual editing, validate print specifications, and either connect to a legitimate printing/fulfillment provider or export a print-ready package/PDF. Claude must research official APIs/SDKs/connectors/white-label services rather than assume they exist. The album data model must remain provider-neutral.
