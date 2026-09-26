# Worker brief: עובד תיוג #1 (Seed Labeling Worker)

Author: Curation & Evaluation Lead #1. Onboarding: by the PM (WORKERS.md interview first). Reservations: **schema v5 + ADR-022** (reserved by the PM for this task).

## One-sentence goal
Let the owner record which photos he wants in an album (must / maybe / no + "special moment") on a fixed sample of ~300 photos, fast with the keyboard, before his trip, without touching the technical-filter labels.

## Why it's separate from review_labels
`review_labels.verdict` means "the filter's technical decision is right" and drives `filtered`/`kept`. A preference label must NOT change the filter outcome or `review_stats`. See `evaluation/LABEL_SCHEMA.md`.

## Scope
1. **Schema v5 (additive)** in `app/db/database.py`: `curation_labels` + `ai_label_proposals`, exactly as the DDL in LABEL_SCHEMA.md. `CREATE TABLE IF NOT EXISTS`, and the I-004 migration backup must run. Bump SCHEMA_VERSION to 5 with a comment.
2. **Repository** (`app/db/repository.py`):
   - `set_curation_label(photo, worthiness, special, stratum, held_out)`: upsert by content_hash; also stores rel_path + capture_time;
   - `get_curation_label`, `delete_curation_label`, `delete_all_curation_labels()` (privacy);
   - `seed_progress(library_id)`: sample total, labeled, per stratum.
3. **Sampling script** `evaluation/make_seed_sample.py` (CLI, reads the DB read-only, writes `evaluation/seed_sample.json`; the file is git-ignored because it contains the owner's file names):
   - a deterministic seed; ~300 items total:
     - `random_kept`: 150 from `kept`, stratified by year-month of capture_time (proportional, at least 1 per month when possible);
     - `filtered`: 70 from `filtered`, spread across the primary reasons (duplicate / screenshot / low_quality / exposure), proportional with a minimum of 10 each when available;
     - `dup_groups`: ~15 whole duplicate groups (~40 photos); these go to the existing side-by-side pick, not the 1/2/3 screen;
     - `nominated`: empty at creation; filled when the owner presses "★ חשובה" anywhere (see screen);
   - `held_out = 1` when `int(content_hash[:8], 16) % 10 < 3` (~30%). Stored per item.
   - Handles small libraries: if a stratum is short, take what exists and report it; never fail.
   - Output: `{version, created_at, library_id, seed, items:[{content_hash, photo_id, stratum, held_out}]}`.
4. **API** (`app/api/routes.py`, new endpoints only):
   - `GET /api/libraries/{id}/seed`: the next unlabeled item + progress (404 with a clear message if there's no sample file);
   - `PUT /api/photos/{id}/curation` body `{worthiness, special, stratum?}`;
   - `DELETE /api/photos/{id}/curation`;
   - `POST /api/photos/{id}/nominate`: adds it to the `nominated` stratum;
   - `GET /api/libraries/{id}/curation/export`: CSV for evaluation.
5. **Screen "תיוג מהיר"** (Hebrew, RTL), reusing the fit-to-screen viewer from the filter-review screen:
   ```
   [ photo fit-to-screen ]                                    147 / 300
   ───────────────────────────────────────────────────────────────────
   באלבום?   1 חובה   ·   2 אולי   ·   3 לא        S רגע מיוחד       ← חזרה
   ```
   - 1/2/3 saves and auto-advances; S toggles "special" before or after (save on toggle); Backspace/← goes back one item and allows a change.
   - NO AI suggestion, scores or technical flags shown (the seed is fully blind).
   - Resumable: progress is persisted, and closing mid-way loses nothing.
   - Also add a "★ חשובה" button in the existing photo viewer → nominate.
   - The I-009 gate: the PM shows the owner this mock first; wiring starts only after approval.
6. **Tests** (`tests/`): the migration v4→v5 (existing DB unchanged + backup made); a curation label never changes `filtered`/`kept` or `review_stats`; label upsert/delete/delete-all; sampling determinism, strata counts, held-out rate, small-library behavior; the API happy path + errors (bad worthiness value, no sample file).

## Out of scope
Any AI proposal generation (the table stays empty); per-request relevance labels; metrics computation (the Curation Lead does that); changing the filter-review screen's behavior.

## Done =
Full suite green; the owner manually labels ~10 photos with the keyboard, closes the app, reopens it and continues; the export CSV opens; `filtered`/`kept` counts are unchanged before/after labeling; ADR-022 appended; the owner approves; commit own hunks only; report the hash to the PM.

## Stop and ask the PM if
The DDL needs to differ from LABEL_SCHEMA.md; the viewer can't be reused without refactoring the filter-review code; the screen needs more than the mock above.
