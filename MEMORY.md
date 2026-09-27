# Project Memory

This file is Claude Code's durable project memory. Keep it short and factual. Update it after meaningful decisions or milestones.

## Product
We are building a general-purpose AI photo curator + album generator. It is not limited to travel. A user may request an album about a person across many years, a relationship, a trip, birthdays, a year, or another theme.

## Core differentiator
The system searches and curates a large photo library automatically before laying out the album.

## Current phase
Milestone 0 and Milestone 1 **complete** (2026-09-27; reopened same day for 3 real bugs found in use, all fixed/merged: `03d3905`, `8f8594b`). Milestone 2 (semantic search) **ACTIVE** — 7a POC in progress comparing SigLIP2 base vs. OpenCLIP xlm-roberta-base-ViT-B-32 against the owner's real library.

## Acting owner (owner, 2026-09-26)
During the owner's (Idan's) Japan trip, **Itay is the temporary full project owner**: he approves commits, opens/closes workers, changes priorities, approves milestone progression (incl. M2), makes implementation and product decisions, and accepts/rejects Advisor recommendations. Operating details, setup and the PM startup instruction: `HANDOFF_TO_ITAY.md`.

## Current state (session handoff, PM #2 → PM #3, 2026-09-27 ~15:00)
- **Full live detail is in ACTIVE_WORK.md's PM HANDOFF section — read that first, this is just the durable summary.**
- Git: main pushed, HEAD `74132d3`+ (7a POC Worker's own commit still pending on top). M1 fully closed (both the original scope and 3 bugs found/fixed later the same day: screenshot JPEG detection, near-dup burst threshold `8f8594b`, cancel-button/OneDrive hang `03d3905`). M2 (semantic search, 7a POC) is ACTIVE.
- Round-0 curation baseline done (`52605af`): the technical filter is safe (0 must/special photos ever wrongly excluded), but ~24% of kept photos are still junk (M4) — that's the number 7a needs to beat. M5 duplicate review done (`1feb0c9`): no hidden-moment merges, 88% auto-keeper agreement.
- New permanent role created 2026-09-27: **אחראי יעילות וסשנים #1 (Efficiency & Sessions Lead)** — separate from the PM, audits usage/context/session-health across the PM and all workers, reports to the PM. Does not decide Roadmap/priorities. Its first recommendation (acted on): hand off the PM at a clean checkpoint rather than a fixed context threshold.
- Owner-observed real bug pattern worth remembering: creating a "new library" for a folder that's already indexed (instead of "rescan") renumbers every photo/group ID and can silently orphan data keyed by ID rather than content hash. Already bit the M5 review tool once; fixed there, but keep it in mind elsewhere.
- Real limitation, on purpose, not a bug: screenshot detection only covers known phone-screen resolutions; near-duplicate merging only handles a ~3s burst window (pHash/dHash), not "same session but subject moved" — that's a future event/session-clustering feature (M4 roadmap), never a duplicate-detection fix (relaxing that threshold further risks merging genuinely different photos, per a real false-merge case already found and avoided, ADR-023).

## Environment facts
- Windows 11, Python 3.12 (`py -3.12`). Venv: `%USERPROFILE%\.ai-photo-album\venv`. Data: `%USERPROFILE%\.ai-photo-album\data` (ADR-003).
- Project folder is inside OneDrive with a Hebrew path — keep derived data/venv out of it.
- Claude desktop app redirects `%LOCALAPPDATA%` for its own processes → never use LOCALAPPDATA for shared paths.
- Git for Windows installed; repo initialized 2026-09-26 on branch `main`; since then pushed to GitHub (`origin` = `idan12333-collab/idananditay`). Author identity is set in the repo-local git config only.
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
- Schema versioning: `meta.schema_version` = 4 (`SCHEMA_VERSION` in `app/db/database.py`; v3 reserved for W2/ADR-016) with hand-written migrations; consider a real migration tool when schema changes become frequent.
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
