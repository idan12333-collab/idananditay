# Project Memory

This file is Claude Code's durable project memory. Keep it short and factual. Update it after meaningful decisions or milestones.

## Product
We are building a general-purpose AI photo curator + album generator. It is not limited to travel. A user may request an album about a person across many years, a relationship, a trip, birthdays, a year, or another theme.

## Core differentiator
The system searches and curates a large photo library automatically before laying out the album.

## Current phase
Milestones 0–1 complete and closed (2026-09-26). Milestone 2 NOT started (owner asked to wait).

## Current state (session handoff)
- Code state: all code saved; 27/27 tests passing (last run 2026-09-26 via `run_tests.bat` path). App verified end-to-end in a browser (scan, stats, filters, duplicate groups, photo detail).
- Last user instruction: housekeeping only; do not start M2 and do not change working code until told.
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
- Schema versioning is minimal (`meta.schema_version` = 1); add real migrations before schema changes reach users.

## Open issues
1. HEIC decoding license (pillow-heif GPLv2 wheels) — must be resolved before any commercial distribution.
2. Threshold calibration on real photos pending.
3. `Git-2.55.0.5-64-bit.exe` installer sits in the project folder (git-ignored); owner may delete it.


## Final product requirement
The product must ultimately be a complete consumer app, not just an AI selector. After curation it must automatically create a real page-by-page photo book, allow visual editing, validate print specifications, and either connect to a legitimate printing/fulfillment provider or export a print-ready package/PDF. Claude must research official APIs/SDKs/connectors/white-label services rather than assume they exist. The album data model must remain provider-neutral.
