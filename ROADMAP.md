# Roadmap

North star: a consumer iPhone app (PhotoKit) that turns a very large personal photo library into a meaningful, editable, print-ready album from a natural-language request. The Windows/local web app is a **validation environment**, not the final architecture. Every milestone must answer: *how does this move us closer to that customer experience?*

Guardrails:
- Originals are never modified, and nothing is deleted automatically.
- Technical quality ≠ album significance.
- Local-first/private where practical.
- Commercially viable dependencies before release.
- AI components stay replaceable.
- Windows decisions must not block iPhone.
- Print stays provider-neutral until a provider is chosen, and it must be a real print workflow, not just a mockup.

**Model/dependency rule (from 2026-09-26):** every model or dependency choice records its commercial-license status, iPhone feasibility, runtime requirements and replaceability in MODEL_REGISTRY.md before adoption.

**Scale targets:** a development benchmark of ~5,000 photos; a scale-validation benchmark of 50,000+ photos.

## ⚠ Curation Quality Track: permanent, high-priority product risk (owner, 2026-09-26)
Core question: given a large real library and an album request, does the system reliably select the photos a human would actually want?

**Owner:** Curation & Evaluation Lead. Defines tests, compares approaches, measures results and finds failure modes. Coordinates implementation through the PM.

**Principle:** falsely excluding a photo the user wants is the most expensive error. Early stages stay conservative: pass more candidates on to ranking rather than "cleaning" aggressively. Technical flaws alone must never remove important moments.

**Evaluation set:** built from the I-008 original-photo library, with owner labels:
- definitely / probably include, neutral, probably / definitely exclude;
- duplicate + preferred copy;
- technically poor but important;
- screenshot/document;
- special event / important moment.

**Tracked failures:**
- good photo wrongly excluded;
- junk wrongly retained;
- wrong duplicate chosen;
- important moment missed;
- too many similar photos;
- insufficient event/person coverage;
- irrelevant photo for the request.

**Approach comparison:** for every candidate, record real-set quality, speed, compute/memory, commercial license, iPhone feasibility, privacy, replaceability and cost. Never choose by demo.

**Evaluation rounds:** each round is compared against the previous baseline.
1. Technical baseline (M1).
2. Semantic relevance (M2).
3. People/pets (M3).
4. Events/place/time (M4).
5. Combined curation (M5).
6. Full album selection (M6).

- [ ] **Gate: curation ready for album generation** (required before M6 depends on curation). The thresholds come from the baseline data, not invented up front. The evidence required is listed in ACTIVE_WORK.md, section "Curation gate evidence".

## Milestone 0 — Foundation ✅ (2026-09-26)
- [x] Initialize repo and Python environment: Python 3.12 venv + `start.bat`; Git repo initialized (branch `main`).
- [x] Create configuration system (`app/core/config.py`, pydantic-settings, `APP_*` env vars)
- [x] Add `.env.example`
- [x] Add structured logging (console key=value, JSON-lines file log)
- [x] Add test framework (pytest, synthetic fixture photos)
- [x] Create basic FastAPI health endpoint (`GET /api/health`)

## Milestone 1 — Photo ingestion & technical filtering ⚠️ REOPENED 2026-09-27 (was marked closed 2026-09-26; owner: "let's admit it, we're back fixing bugs in it now" — honest status, not closed). Real bugs found in the owner's actual use, being fixed now: screenshot detection misses JPEGs at a known screen resolution (mislabeled as exposure issues instead), near-duplicate bursts ~1s apart aren't merged (pHash/dHash AND-threshold too strict for real noisy pairs), and the scan cancel button silently does nothing when a file hangs (pool.map blocks the cancel check). See Quality Worker #2 and W2 in ACTIVE_WORK.md. Will re-close once these are fixed, tested and owner-approved.
*Definition of done: the technical-filtering implementation is stable enough to continue. It does NOT mean the photo-selection problem is solved; that's tracked by the Curation Quality Track.*
Customer value: point the app at a library, and it's indexed safely; obvious technical rejects are suggested (never deleted); the user reviews and corrects the suggestions quickly.
- [x] Scan folder recursively (skips hidden/system folders, Unicode/Hebrew paths)
- [x] Support JPEG/PNG and practical HEIC handling (+ WebP; HEIC via pillow-heif = POC_ONLY license, see MODEL_REGISTRY)
- [x] Extract EXIF/date/dimensions/GPS (date fallback: EXIF → filename → file mtime, source recorded)
- [x] Generate thumbnails (EXIF-oriented, content-hash keyed, outside OneDrive)
- [x] Compute exact hash (SHA-256) and perceptual hash (pHash + dHash)
- [x] Detect near duplicates (groups + "best" photo per group; nothing deleted)
- [x] Basic technical quality signals (tile sharpness, exposure, low-res, screenshot detection; transparent classical score = the first version of the M5 quality scorer)
- [x] Persist to SQLite (incremental rescans, missing-file tracking, job progress)
- [x] Local inspection UI (Hebrew RTL); tests with fixture images
- [x] Bugfix: folder B showed folder A's photo (never-reused IDs + versioned image URLs, ADR-012; single-instance server, ADR-013)
- [x] UX: in-app folder browser (ADR-014); build-versioned assets + "new version" banner (ADR-015)
- [x] **Filter review screen** "מה הסינון הציע?" (committed `a9783bb`): a summary by reason, a batch review, one-tap restore / remove, a duplicate keeper pick (exactly one copy per group), neutral wording. The filter makes technical judgments only; album relevance comes from M2+. The old technical gallery sits behind debug mode. Print suitability is internal-only. (ADR-017, ADR-018, schema v4; 89 tests).
- [ ] **Pre-scan exclusions**: mark folders/files that are never scanned (ADR-016, schema v3). Unblocked (filter review committed); partial work exists only on the owner's PC.
- [x] Owner accepted the filter-review version as good enough to move on (2026-09-26). Further tuning happens later, from real use and more owner feedback. Not a blocker.

### Filter follow-ups (from the owner's tests, 2026-09-26; to be scheduled later, not blocking)
- [ ] Screenshot false positives (different from the false NEGATIVES below): the rule is "PNG at a phone-screen size without camera EXIF". Real screenshots that contain people (a contact card, an Instagram post) are technically correct flags, but the owner wants them. Revisit with M2/M3 people signals ("screenshot but contains people → suggest keep").
- [~] **IN PROGRESS 2026-09-27 (M1 reopened, Quality Worker #2):** screenshot false NEGATIVES — JPEGs at a known screen resolution without camera EXIF weren't detected at all and got tagged as exposure issues instead. Confirmed real examples in the owner's library.
- [~] **IN PROGRESS 2026-09-27 (M1 reopened, Quality Worker #2):** near-duplicate bursts (~1s apart, same camera) aren't merged — pHash fails the ≤8 threshold on ~55 real pairs even though dHash agrees. Fix: time-windowed threshold (ADR-023), not a global relaxation (would cause real false-merges).
- [~] **IN PROGRESS 2026-09-27 (M1 reopened, W2):** the scan "cancel" button is a silent no-op when a file in the current analysis chunk hangs (e.g. an undownloaded OneDrive file) — `pool.map`'s cancel check never runs until the whole chunk returns.
- [ ] Calibrate blur (too lenient: IMG_1160 is out of focus and wasn't flagged), brightness (white-background screenshots flagged "too bright"), and the overall technical-quality score, using the owner's review labels / agreement table.
- [ ] Important photo with weak technical quality: never let technical flags alone exclude a photo that's significant to the request. Once M5 relevance/significance exists, it should be able to override technical suggestions.
- [ ] Wording review of the filter screen after real use (neutral, non-technical).
- [ ] The print-simulation patch comes from the image center and sometimes lands on plain areas. Revisit when print suitability is used internally (M6/M8).

### Known validation limitations (not M1 blockers)
- Copying photos from an iPhone to Windows via the photo folder produced tiny preview files (~160 px), videos with image extensions, empty files and AAE edit sidecars. This is a limitation of the Windows test setup; we won't build a workaround importer. The iPhone/PhotoKit architecture (M10) must access **original assets** correctly: full-resolution originals, the user's edited versions, Live Photos (image + video pair), and iCloud-only assets.

### Technical debt / follow-ups (not blocking)
- [x] Install Git for Windows, `git init`, first commit
- [ ] Friendlier ingest errors ("this is a video / empty file" instead of "cannot read image")
- [ ] Scanner: warn before scanning OneDrive cloud-only files (scan downloads them)
- [ ] Near-duplicate comparison is O(n²): fine to ~20–30k photos; needs an index (BK-tree/multi-index) before the 50k+ benchmark
- [ ] Resolve HEIC decoder licensing before commercial distribution (see MODEL_REGISTRY)
- [ ] Replace `httpx` TestClient dependency warning (Starlette suggests `httpx2`)

## Milestone 2 — Semantic photo search (NEXT; not started, needs the owner's approval)
Customer value: find photos by describing them ("ים", "יום הולדת"), the foundation for album requests.
- [ ] Implement the embedding provider interface
- [ ] Choose a POC embedding model and record license / iPhone feasibility / runtime / replaceability
- [ ] Index image embeddings
- [ ] Text-to-image search
- [ ] Search filters by date
- [ ] Basic retrieval evaluation (precision@K on labeled samples)

## Milestone 3 — People & pets
Customer value: "an album of my son / of us / of our dog" works across years.
- [ ] Face provider interface
- [ ] Face detection + face embeddings
- [ ] Reference-person workflow (multiple reference photos across ages)
- [ ] Similarity matching with an uncertain-match state; configurable thresholds
- [ ] Human confirmation UI
- [ ] Person-match evaluation
- [ ] **Pets**: detection + matching of the user's own pets from reference photos (same uncertainty + confirmation model)
- [ ] **Privacy controls for person/face data** (moved here from M10): view and delete a person's reference photos, embeddings and matches; delete all face data of a library; face data is removed together with its library

## Milestone 4 — Events, timeline & places
Customer value: "the Japan trip", "birthdays", "2026" become findable groups.
- [ ] Time-based clustering
- [ ] GPS-assisted clustering
- [ ] **GPS → place names** (country/city/place), local/offline where practical; no precise locations sent out without a separate privacy decision
- [ ] Semantic cluster refinement
- [ ] Event browser
- [ ] Year/month/event coverage metrics

## Milestone 4.5 — Album request understanding
Customer value: the user writes a request in their own words, and the system knows who / when / where / what theme / how big.
- [ ] Parse a natural-language request into a structured album intent (people/pets, date range, places, events/themes, album size, tone)
- [ ] Provider-neutral interface. Sending the **request text only** to an external AI service is acceptable in principle. Photos, face embeddings, precise locations and other sensitive media-derived data are never sent without a separate explicit architecture/privacy decision.
- [ ] Clarifying questions when the request is ambiguous
- [ ] Evaluation on a set of example requests

## Milestone 5 — Curation engine
Customer value: the top N photos tell the story, not just the prettiest ones.
- [ ] Quality scorer (extends the M1 classical signals)
- [ ] Aesthetic scorer adapter
- [ ] Query relevance score
- [ ] Person/pet relevance score
- [ ] **Album-significance / human-interest signals**: people together, expressions, interaction, important events, uniqueness, relevance to the request. (The system doesn't claim to know "emotional value"; that belongs to the user.)
- [ ] Duplicate penalty
- [ ] Diversity selection + coverage constraints
- [ ] Explain selection reasons
- [ ] Human keep/reject feedback
- [ ] Acceptance-rate evaluation

## Milestone 6 — Album generation
- [ ] Story sections
- [ ] Layout template system
- [ ] Hero/supporting photo rules (uses internal print suitability from M1)
- [ ] Face-aware/saliency-aware crop
- [ ] Editable page representation
- [ ] HTML preview
- [ ] PDF export

## Milestone 7 — Product validation
- [ ] Development benchmark: ~5,000 photos
- [ ] Scale-validation benchmark: 50,000+ photos (runtime, memory, incremental rescans)
- [ ] Person-over-years test
- [ ] Trip test
- [ ] Theme/event test
- [ ] Measure runtime per 1,000 photos
- [ ] Measure curator acceptance rate
- [ ] Collect failure cases
- [ ] Iterate weights/algorithms

## Milestone 8 — Production album editor
- [ ] Visual page-by-page editor
- [ ] Replace/reorder/crop photos
- [ ] Cover/back/spine model
- [ ] Album size/page-count configuration
- [ ] Print resolution warnings (built on the internal print-suitability service)
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
- [ ] Native iOS PhotoKit integration: original-asset access (full-resolution originals, edited versions, Live Photos, iCloud-only assets); see the M1 validation limitation
- [ ] Production onboarding
- [ ] Project library/save-resume
- [ ] Account-level privacy/delete controls (the person/face-data controls ship in M3)
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
