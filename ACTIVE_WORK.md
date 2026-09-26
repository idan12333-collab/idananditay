# Active Work — live coordination board

Source-of-truth split: **Git** = code state · **MEMORY.md** = project state · **ACTIVE_WORK.md** = live multi-session coordination.
Maintained by the Project Manager (PM) session. Workers: read this before touching code; message the PM on every status change.
Last updated: 2026-09-26 ~14:55 (PM). Git-verified corrections by Cloud Handoff Worker #1 (cloud session, 2026-09-26), pending PM review — see `project_management/handoffs/2026-09-26_cloud_handoff_for_pm.md`.

## Snapshot
- Branch `main`, pushed to GitHub (`origin` = `idan12333-collab/idananditay`). HEAD = `64d099a` (W4, ADR-020) on top of `6a7a1eb` (PM docs), `a9783bb` (W1) and `55b7761` (W3); previously `7927635` (folder browser + build-versioned assets).
- Working tree (owner's PC): W1, W3 and W4 are committed. Only W2 (partial) is uncommitted, and it exists ONLY on the owner's PC — not in GitHub. **Never** `git add -A` / `commit -a`: each worker stages only its own hunks.
- Milestones: M0 and M1 closed (except W2's pre-scan exclusions). **M2 NOT started.** M2 requires: a decision on W2 (finish+commit, push as a WIP branch, or shelve), a clean tree, and explicit approval by the owner — or by Itay as acting owner (see below).
- Plan usage (shared by all sessions): 5-hour window 58% used, resets 15:40 UTC; weekly 15%.

## Acting owner during the Japan trip (owner, 2026-09-26)
- Itay is the **temporary full project owner** while Idan is away. Everywhere this file says "owner", Itay's approval counts. He approves commits, opens/closes workers, changes priorities, approves milestone progression (incl. M2), makes implementation/product decisions and accepts/rejects Advisor recommendations.
- The PM runs on Itay's computer as the next Project Manager (see WORKERS.md, `HANDOFF_TO_ITAY.md`). Cloud sessions work on their own branches; only the PM on Itay's machine merges to `main`. Cloud workers follow the "Cloud-worker rule" in WORKERS.md (PM = coordination hub; every task ends with a "Handoff to Project Manager").

## Coordination protocol (owner-approved 2026-09-26)
1. The PM session is named **"project manager"**. All sessions run in **auto** mode: cross-session messages and idle notices only flow automatically when the modes match. If a session is in a different mode, the PM tells the owner which one to switch.
2. Every worker messages "project manager" when it: finishes · is blocked · needs a handoff · has test failures that affect another worker · is about to commit. Each message includes the test result, the exact file/hunk list, and the manual-test steps.
3. The PM subscribes to one-shot idle notices. No polling, cron, daemons, or extra processes without the owner's approval.
4. Before starting implementation, a worker checks `git status` and this file, then confirms that its scope doesn't overlap an ACTIVE row.
5. Commit gate: full test suite passes → owner validates manually (for user-facing work; during the Japan trip Itay acts as owner) → owner approves either in the worker's session OR explicitly to the PM, who relays it quoting the owner's words (owner-authorized 2026-09-26) → the worker commits its own hunks only → the staged tree is verified on its own (`git stash --keep-index` + full suite) → the worker reports the hash to the PM.
6. Context: the PM checks each worker's context with get_usage before assigning work. At ≥70% no new large task. At ≥85% stop at a clean checkpoint and hand off to a fresh worker (handoff notes go here and in MEMORY.md).
7. The PM hands itself off the same way: before it gets near its limit, it writes the full state here and in MEMORY.md.

## Efficiency & vision rules (owner, 2026-09-26 evening; additive to the protocol above)
- Optimize waste, not rigor. Keep workers to a minimum. Run in parallel only when the tasks are truly independent (no shared files, schema or UI/API) and it clearly saves time. Prefer one complete brief over many small messages. Read state files instead of long transcripts. Reuse fixtures/datasets.
- Tests: targeted tests while building; the full suite at checkpoints and before any commit.
- Workers are replaceable. A worker that finishes its scope becomes DONE and is closed; it doesn't get unrelated new work. When a context has built up a lot of irrelevant history → safe checkpoint → handoff to a fresh worker (compact only when it's genuinely useful). The same rule applies to the PM.
- Usage window: near the short limit, start no large task; finish safe units, save state, prepare the resume. After a reset, resume the highest-value unblocked work first.
- PM idle-notice subscriptions: only when a worker would NOT report by itself. Workers report on their own (saves duplicate PM turns).
- The PM owns ROADMAP.md as the path to the final vision (consumer iPhone app, huge libraries, natural-language albums, people/pets/events/places, age-robust faces, emotional value ≠ technical quality, curation, page layout, editing, print-ready output, ordering). Factual updates happen automatically. Major strategic changes need the owner's approval first. Good ideas that fall outside the current milestone go to the backlog, not to a new worker.
- The daily report includes "יעילות העבודה היום". The dashboard shows an efficiency section.

## Usage investigation (2026-09-26 ~17:45, measured from the transcripts' API usage fields since the reset ~17:15)
- Dashboard Worker: 61 requests, 12.0M cache-read, peak context 275k, 13 browser batches with screenshots, 9 pytest runs.
- W1: 18 requests, 7.2M cache-read, peak context **466k** (~0.4M re-read per step).
- PM: 24 requests, 5.7M cache-read, peak context 267k.
- W2: 0 (idle, which is correct).
- Total: ~103 requests / ~25M cache-read in ~30 min, versus 13.9M in the whole previous 24h.
- Root cause: large contexts × many small steps. Every request re-reads the whole cached context. Contributors: visual browser self-checks with screenshots, repeated test runs, multiple owner-feedback rework rounds, PM turns on idle notices.
- Not a cause: the dashboard server (local, zero Claude usage), W2 (idle), polling/cron (none).
- Caveat: the 25M figure is the sum of per-request cache_read over the transcripts of 3 sessions (this project only). The 13.9M/24h figure came from the owner's usage report, whose scope and accounting are unknown. The comparison is indicative, not exact.
- **Operating rules (refined by the owner, 2026-09-26):**
  - Normally ONE active implementation worker at a time. Waiting workers stay truly idle. No polling. Workers send concise reports to the PM.
  - Feedback is batched into meaningful correction rounds.
  - Worker reuse is decided case by case. Reuse a worker when the next task is closely related, its context is still relevant, and reuse is cheaper than rebuilding the context. Otherwise use a fresh worker.
  - ~300k context is a WARNING threshold, not a cutoff. Weigh how relevant the context is against the remaining work. Close high-context workers once their scoped work reaches a clean checkpoint.
  - Tests: targeted tests during implementation, whenever they're useful. The full regression suite runs at the final checkpoint before a commit.
  - Visual (browser/screenshot) testing: batched and minimized. Another run is fine when it's genuinely needed.
  - PM handoff: based on actual inefficiency (context relevance, cache/request behavior), not on a fixed number.
  - The PM doesn't react to idle notices when a worker reports on its own.
  - **Error recovery (owner-requested 2026-09-26):** the PM holds a one-shot idle subscription ONLY on workers that are actively implementing. When a notice arrives without a report from that worker, the PM checks the transcript tail. If the turn ended on an API/network error, the PM sends one "continue from where you stopped" message; if it fails again, the PM tells the owner. No polling. Limitation: if the internet or the Claude API is down for everyone, the PM can't react until it's back.

## Worker identity & onboarding (owner, 2026-09-26)
- Permanent numbering per category (never reused) and the full history live in **WORKERS.md**. New workers pass a one-exchange onboarding interview + get the standing efficiency rules (see WORKERS.md) before they write any code. Final states: DONE / RETIRED / REPLACED / FAILED. Replacing a worker: final status → reason → handoff → next number → interview → then work.
- Current mapping: W1 = Quality Worker #1, W2 = Exclusions Worker #1, W3 = Dashboard Worker #1, W4 = Dev Reload Worker #1 (planned), PM = Project Manager #1.

## Workers

### W1: Quality / print suitability / human review viewer. Status: DONE — committed as `a9783bb` (see WORKERS.md). History below: (fix round 3 after owner test #3, 17:20): per-reason restore / one keeper per duplicate group (a real leak bug), one place per photo, merge blur+small into "איכות ירודה", "שרופה"→"בהירה מדי", neutral wording, investigate screenshot false positives. Context 42%.
- Rework delivered: a filter-first review ("מה הסינון עשה?" with a summary by reason, a batch grid, restore/"should have filtered", side-by-side duplicate picks in a new `duplicate_picks` table, the `auto_best_photo_id` column) and a simplified viewer. Still schema v4 (additive). ADR-018 revised. The PM verified 87/87 tests. The split still works.
- Calibration findings (for later): blur rule too lenient (IMG_1160 is out of focus but not flagged); white screenshots flagged "too bright"; the MROC7762 rotation is in the file itself, not our bug.
- Owner feedback: the photo was shown tiny (160×120 at native size) and the panel was far too technical. The owner wants it simple and interactive. Spec sent by the PM: fit-to-screen, one plain-Hebrew verdict with a traffic-light color, an interactive print-size picker with a visual preview, 👍/👎 labeling with reasons only after 👎, and technical details collapsed. Also check a possible 90° rotation. Backend unchanged. Still NO commit.
- Session: "עובד איכות" (`local_a74829e2-41be-4774-904d-cb88a891e546`). Mode: auto. Context: 28% (low risk).
- Starting commit: `7927635`.
- Scope: print-suitability rating (`app/printing/`), revised classical quality, full-screen review viewer with human labels, agreement table, and CSV export.
- Owns: schema **v4** (drop `photos.is_low_res`, recompute `quality_score`, add a `review_labels` table); **ADR-017** (print suitability) and **ADR-018** (review labels); `app/printing/`, `app/vision/*`, `analyzer.py`, `duplicates.py`, `pipeline.py` (AnalyzeConfig), `config.py`, `main.py`, `__main__.py`, `routes.py` (everything except W2's hunks), web static files (viewer/filters/stats), the W1 hunks in `database.py`/`repository.py`, its tests, and its doc updates.
- State: 84/84 tests pass. The PM re-ran them on the shared tree and they passed. The W1-only split was dry-run in an isolated worktree: 84/84 pass, no W2 identifiers left.
- Pending: the owner's manual test (7 steps, given to the owner) → the owner writes "approved, commit" **in W1's session** → W1 commits using synthesized W1-only blobs for database.py/repository.py → reports the hash plus the result of the isolated check.
- Safety: the owner's DB was backed up before the v4 migration: `%USERPROFILE%\.ai-photo-album\backups\library_before_v4_2026-09-26.sqlite3` (116 photos).
- Known finding (not a bug, calibration later): the 160-px files get sharpness 100/100.

### W2: Pre-scan exclusions. Status: WAITING (on W1's commit)
- Session: "עובד החרגות" (`local_028eae54-f07c-4076-8f47-8692a8134014`). Mode: auto. Context: 21% (low risk).
- Starting commit: `7927635` (must re-read the new HEAD when it resumes).
- Scope: in the folder browser, mark files/folders to exclude before scanning. Excluded files are never read or indexed. The list is stored per library.
- Owns: schema **v3** (the `library_exclusions` table, the `excluded` photo status) and **ADR-016**; `scanner.py`, `folder_browser.py`, `app/api/browse.py`, the exclusion code in `database.py`/`repository.py`; in `pipeline.py` only the scan/missing part of `IngestionPipeline.run()` plus `IngestSummary.excluded`; in `routes.py` only `LibraryCreate.exclude` + `create_library()` + `GET /api/exclusions`; in the UI only the folder-browser dialog, the section-1 card, a styles block appended at the end, and an optional exclusions stats tile.
- Done (uncommitted): the scanner skip + path validation, schema-v3 DDL, repository methods, the video-extension list moved to the scanner.
- Remaining: wiring into the pipeline, API, UI, tests, ADR-016, and docs.
- Resume condition: W1 committed and verified by the PM → the PM sends "continue" → W2 re-reads the git log, this file, and the shared files → finishes → full suite → owner validates manually → separate commit of W2's hunks.
- Important: the owner DB goes straight to v4 without a v3 step. v3 must stay additive (`CREATE TABLE IF NOT EXISTS`). Any real data migration must key off table existence or use v5.

### W3: Dashboard Worker (project-management control center, dev tooling). Status: DONE — committed as `55b7761`. History: (awaiting the owner's manual test, 17:30). 40/40 own tests pass. The product suite is untouched (88 pass). It will commit only its own paths after approval, and then close.
- Session: "Dashboard Worker" (`local_e2492d03-fa5c-4973-943e-6e50128324d7`). Mode: auto. Context: fresh.
- Starting commit: `7927635`.
- Scope: a local-only Hebrew dashboard on 127.0.0.1:8790 (stdlib Python + static files). Read-only views of git, the docs, state.json and the transcripts. Actions are prepared requests for the PM (inbox.jsonl + Copy + "open PM"). No watchers or polling of Claude.
- Owns ONLY: `project_management/**`, `start_project_manager.bat`, minimal `.gitignore` lines. Never touches `app/`, `tests/` or the product docs. Commits only its own paths.
- Reservations: **ADR-019** (dashboard tooling decision; may be recorded in `project_management/README.md` + a one-paragraph ADR, the PM appends it to DECISIONS.md). No schema.
- Depends on: nothing. Blocks: nothing. Runs in parallel with W1/W2.
- Contract: the PM writes `project_management/state.json` and `project_management/daily/*.md`. W3 defines the schema.
- Completion condition: its own tests pass + the product suite is still green → the owner validates manually → the owner approves in W3's session → a separate commit.

### W4: Dev Reload Worker (dev tooling). Status: implementation committed as `64d099a` (ADR-020). The worker's final status/lessons are not in Git — PM to confirm. History below: (owner-approved 2026-09-26)
- Start conditions:
  - W1 AND W3 have been validated by the owner and committed;
  - a clean tree;
  - enough short-window quota to reach a safe checkpoint (otherwise it waits for the next reset);
  - the owner opens a fresh session named "Dev Reload Worker" (the PM can't create sessions).
- Scope:
  - a separate `start_dev.bat` + a stdlib watcher/supervisor for BOTH the album app and the dashboard;
  - the watcher detects a change → stops the old child → verifies the process has exited and the port is free → starts a new one → verifies the new build/pid via the health endpoint;
  - in dev mode the page auto-refreshes on a build change (fast check);
  - normal `start.bat` / `start_project_manager.bat` behavior is unchanged;
  - ADR-013 single-instance protection + build/PID health checks are preserved.
- The owner's hard requirements:
  - the watcher tracks ONLY code/UI files (.py, .html, .js, .css under app/ and project_management/). It never watches the DB, thumbnails, logs, caches, backups, .git or OneDrive temp files;
  - debounce;
  - a regression test proves that a restart in the middle of a scan can never leave that scan marked "completed". It must end up interrupted/failed and be safely re-runnable;
  - a test that an old process can't keep serving while the new one fails to bind.
- Reservation: ADR-020. No schema, unless a job-status value is needed; that takes v5 after an ADR note.

## Dependencies
- W2 → W1 commit: satisfied (`a9783bb`). W2 must rebase its local work on the current HEAD (shared files: database.py, repository.py, pipeline.py, routes.py, app.js, index.html, styles.css).
- M2 → a W2 decision + clean tree + approval by the owner or Itay (acting owner).

## Reservations
- Schema: v3 = W2 (uncommitted), v4 = W1 (committed). **Next free: v5.**
- ADR: 016 = W2 (uncommitted), 017 = W1, 018 = W1, 019 = W3 (dashboard), 020 = W4 (dev reload, committed). **Next free: ADR-021.**

## Backlog (unassigned, not started)
- Warn before scanning OneDrive cloud-only files (natural follow-up to W2; assign after W2).
- Calibrate the quality thresholds on a real library (the review labels from W1 make this measurable; do it before or with M2).
- HEIC decoder licensing (pillow-heif = POC_ONLY).
- `httpx` TestClient deprecation warning.
- The duplicate file `PRINT_INTEGRATION (1).md` (the owner may delete it).
- ~~CLAUDE.md rule 1a~~: committed in `6a7a1eb`.

## Product direction update (owner, 2026-09-26 ~17:25), SUPERSEDES the "people & animals = memories" wording below
- The rule-based filter makes only technical judgments. Its wording is neutral ("הסינון הציע להוציא" / "פחות מתאימה כרגע לאלבום"). Relevance (landscapes, objects, even screenshots) is decided later by the album request + semantic signals (M2+). Sent to W1.

## Product direction update (owner, 2026-09-26 ~15:25)
- The album's goal is photos of **people and animals**. Everything else is irrelevant. Detecting people/animals needs an ML model, so it belongs to M2/M3 and requires a license check plus the owner's approval of M2. The PM flagged to the owner that trip albums may want landscapes too.
- Print size / PPI must be **invisible to the customer**. It stays internal (automatic layout decisions later). W1 is removing it from the UI (ADR-017 → internal-only).
- The "tiny" photos are tiny on disk (160 px, ~6 KB). Our ingest doesn't degrade them. CONFIRMED by the owner (15:30): copying from the iPhone photo folder to Windows produces low-res files. Deferred task T6: research the correct import path (iPhone "Keep Originals" setting / Windows Photos import / iCloud / OneDrive camera upload) + warn customers when the imported files look like previews. This is also an input to the future PhotoKit design.
- PM HANDOFF NOTE (15:30, quota near 100%, resets 18:40): W1 is processing the direction message (hide print size, "not a memory" framing, delete-bug fix already done; 88 tests at the last report; NO commit). W3 is paused cleanly (sources done; next: tests → server → UI). W2 is waiting. After the reset: check W1's report → owner manual test → W1 commit → resume W2 → resume W3.
- The current filter is rules-based, not ML, and doesn't learn. Feedback labels are stored for calibration and future learning.

## Product direction for filtering/review (owner, 2026-09-26)
Goal: filtering is effective, **no photo is ever lost**, and the customer can comfortably review what the filter did and give feedback. Core screen = review of the filter's decisions: a summary by reason, a batch grid review, one-tap restore/disagree, a side-by-side duplicate pick; a single-photo viewer only for doubtful cases. Sent to W1 as the rework priority.
