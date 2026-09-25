# Roadmap

## Milestone 0 — Foundation ✅ (2026-09-26)
- [x] Initialize repo and Python environment — Python 3.12 venv + `start.bat`; Git repo initialized (branch `main`).
- [x] Create configuration system (`app/core/config.py`, pydantic-settings, `APP_*` env vars)
- [x] Add `.env.example`
- [x] Add structured logging (console key=value, JSON-lines file log)
- [x] Add test framework (pytest, synthetic fixture photos)
- [x] Create basic FastAPI health endpoint (`GET /api/health`)

## Milestone 1 — Photo ingestion ✅ (2026-09-26)
- [x] Scan folder recursively (skips hidden/system folders, Unicode/Hebrew paths)
- [x] Support JPEG/PNG and practical HEIC handling (+ WebP; HEIC via pillow-heif = POC_ONLY license, see MODEL_REGISTRY)
- [x] Extract EXIF/date/dimensions/GPS (date fallback: EXIF → filename → file mtime, source recorded)
- [x] Generate thumbnails (EXIF-oriented, content-hash keyed, outside OneDrive)
- [x] Compute exact hash (SHA-256)
- [x] Compute perceptual hash (pHash + dHash)
- [x] Detect near duplicates (groups + "best" photo per group; nothing deleted)
- [x] Basic blur/quality signal (tile sharpness, exposure, low-res, screenshot detection, transparent quality score)
- [x] Persist to SQLite (incremental rescans, missing-file tracking, job progress)
- [x] Local gallery/index inspection UI (Hebrew RTL; filters, year histogram, duplicate groups, photo details)
- [x] Tests with fixture images (27 tests)

### Open follow-ups from M0–M1 (not blocking)
- [x] Install Git for Windows, `git init`, first commit
- [ ] Calibrate blur/exposure/screenshot thresholds on a real photo library
- [ ] Resolve HEIC decoder licensing before commercial distribution (see MODEL_REGISTRY)
- [ ] Replace `httpx` TestClient dependency warning (Starlette suggests `httpx2`)

## Milestone 2 — Semantic photo search (NEXT — not started)
- [ ] Implement embedding provider interface
- [ ] Choose POC embedding model and record license
- [ ] Index image embeddings
- [ ] Text-to-image search
- [ ] Search filters by date
- [ ] Basic retrieval evaluation

## Milestone 3 — People
- [ ] Face provider interface
- [ ] Face detection
- [ ] Face embeddings
- [ ] Add reference-person workflow
- [ ] Similarity matching
- [ ] Uncertain match state
- [ ] Multiple reference ages
- [ ] Human confirmation UI
- [ ] Person-match evaluation

## Milestone 4 — Events and timeline
- [ ] Time-based clustering
- [ ] GPS-assisted clustering
- [ ] Semantic cluster refinement
- [ ] Event browser
- [ ] Year/month/event coverage metrics

## Milestone 5 — Curation engine
- [ ] Quality scorer
- [ ] Aesthetic scorer adapter
- [ ] Query relevance score
- [ ] Person relevance score
- [ ] Duplicate penalty
- [ ] Diversity selection
- [ ] Coverage constraints
- [ ] Explain selection reasons
- [ ] Human keep/reject feedback
- [ ] Acceptance-rate evaluation

## Milestone 6 — Album generation
- [ ] Story sections
- [ ] Layout template system
- [ ] Hero/supporting photo rules
- [ ] Face-aware/saliency-aware crop
- [ ] Editable page representation
- [ ] HTML preview
- [ ] PDF export

## Milestone 7 — Product validation
- [ ] Test on 1k photos
- [ ] Test on 5k+ photos
- [ ] Person-over-years test
- [ ] Trip test
- [ ] Theme/event test
- [ ] Measure runtime
- [ ] Measure curator acceptance rate
- [ ] Collect failure cases
- [ ] Iterate weights/algorithms

## Milestone 8 — Production album editor
- [ ] Visual page-by-page editor
- [ ] Replace/reorder/crop photos
- [ ] Cover/back/spine model
- [ ] Album size/page-count configuration
- [ ] Print resolution warnings
- [ ] Bleed and safe-zone support
- [ ] Save/resume editable projects
- [ ] Provider-neutral print specification model

## Milestone 9 — Printing & fulfillment integration
- [ ] Research current photo-book/print-on-demand providers
- [ ] Check official API/SDK/white-label capabilities
- [ ] Check whether any legitimate connector/MCP is useful
- [ ] Record findings in PRINT_INTEGRATION.md
- [ ] Implement provider adapter interface
- [ ] Provider-specific print profile
- [ ] Print-ready validation
- [ ] Price/quote integration if supported
- [ ] Order submission if supported
- [ ] Shipping/order-status integration if supported
- [ ] Print-ready PDF/package fallback

## Milestone 10 — Consumer application
- [ ] Native iOS PhotoKit integration
- [ ] Production onboarding
- [ ] Project library/save-resume
- [ ] Privacy/delete controls
- [ ] Accounts
- [ ] Payments
- [ ] Order flow
- [ ] Production error handling
- [ ] App analytics/observability
- [ ] App Store readiness

## Later / optional
- [ ] cloud processing option
- [ ] Android
- [ ] family/shared albums
