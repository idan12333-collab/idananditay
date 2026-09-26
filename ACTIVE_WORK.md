# Active Work — live coordination board

Source-of-truth split: **Git** = code state · **MEMORY.md** = project state · **ACTIVE_WORK.md** = live multi-session coordination.
Maintained by the Project Manager (PM) session. Workers: read this before touching code; message the PM on every status change.
Last updated: 2026-09-26 ~14:55 (PM). Git-verified corrections by Cloud Handoff Worker #1 (cloud session, 2026-09-26), pending PM review — see `project_management/handoffs/2026-09-26_cloud_handoff_for_pm.md`.

**PM #2 ACTIVE since 2026-09-26 ~23:15: "מנהל פרוייקט #2" (`local_ae3d6b14-31cd-4284-a516-321e510e7a64`). Workers report here, not to PM #1. עובד תיוג #1 has been notified.**

## >>> PM HANDOFF: READ THIS FIRST, Project Manager #2 (written by PM #1, 2026-09-26 ~23:10) <<<
- **Why the handoff:** PM #1 reached ~540k context and became the biggest usage consumer (84 requests / 41M cache-read since the 22:10 reset). Per I-010, PM #2 runs on a cheaper model for routine coordination and escalates to a strong model for complex decisions.
- **Git:** main = origin/main, pushed; HEAD ≥ a08601b. M1 is CLOSED (a398ca7). Only the labeling worker's changes may be uncommitted.
- **Owner:** Idan flies **Monday 2026-09-28**. From then on **Itay is the acting owner** (HANDOFF_TO_ITAY.md). Only one PM writes to main.
- **Active:**
  - **עובד תיוג #1** (`local_73ba90f8-59c2-4511-aaaa-be8da01ba263`): schema v5 + ADR-022, READY FOR OWNER TEST (not committed). 173/173 tests pass (12 new). Reports now to PM #2. Waiting on the owner's manual test (5 steps below) before commit.
  - **Idan:** importing ~500 ORIGINAL photos (evaluation/LIBRARY_SPEC.md) and then labels the ~300-photo seed BEFORE the flight.
- **Waiting (wake at checkpoints only):**
  - **אחראי בקרת איכות תמונות #1** (`local_eaba79d0-…`): next is evaluation/metrics.py, the round-0 baseline, after the worker's v5 commit + the seed labels.
  - **יועץ מוצר ויעילות #1** (`local_3c7e1461-…`).
  - **Cloud Worker #1** ("פרויקט ביקורת ענן"): no task. The owner relays messages; the PM writes the exact text.
- **Next after the seed:** baseline (curation lead) → the 7a POC (SigLIP 2 base vs OpenCLIP XLM-R B/32; verify licenses locally first) → Advisor review → I-013 concierge album (gated) → 7b people POC. Itay's second library (I-016) needs Itay's consent.
- **Pending triggers:** none scheduled. Subscribe to a one-shot idle notice on active workers only. Cron is session-only; re-create any triggers you need yourself.
- **Owner communication style:** simple Hebrew, short; ask only real questions; the owner isn't the reminder system; state exactly which session to open and nothing more.

## Scheduled triggers (standing rule: the PM schedules every known follow-up itself; the owner isn't the reminder system)
| Trigger | Mechanism | Fires | Action | Must stay alive | If it fails |
|---|---|---|---|---|---|
| Quota reset | CronCreate one-shot `ff6d0cf7` in the PM #1 session | 2026-09-26 22:13 | Check usage → resume Exclusions #1 with the full brief + I-004 → update state → 2 lines to the owner | Claude app open, computer awake, PM #1 session open and idle | The trigger is lost; the owner writes anything to the PM, and the PM runs the same steps |
| Advisor first review | CronCreate one-shot in the PM #1 session | 2026-09-26 22:17 | Wake Advisor #1 → ≤5 ideas → joint classification → only product-owner items go to the owner | Same as above | The owner writes to the PM, and the PM runs the review then |
| Worker finishes / network error | The worker reports + a one-shot notify_when_idle | On idle | Verify → next step / resend "continue" | Same | The owner tells the PM that a worker looks stuck |
| Exclusions #1 committed (M1 closes) | The PM handles the worker's report | On the report | Wake Advisor #1 for the M1 review; then propose the PM #2 handoff | Same | — |
| PM handoff | The PM asks the owner to open "Project Manager #2" | After M1 closes | The new PM re-creates any pending cron triggers in its own session | — | Cron jobs are session-only: re-create them after a handoff |

## Snapshot
- Branch `main`, pushed to GitHub (`origin` = `idan12333-collab/idananditay`). HEAD = `64d099a` (W4, ADR-020) on top of `6a7a1eb` (PM docs), `a9783bb` (W1) and `55b7761` (W3); previously `7927635` (folder browser + build-versioned assets).
- Working tree (owner's PC): W1, W3 and W4 are committed. Only W2 (partial) is uncommitted, and it exists ONLY on the owner's PC — not in GitHub. **Never** `git add -A` / `commit -a`: each worker stages only its own hunks.
- Milestones: M0 complete; M1 **almost complete — pending exclusions completion (W2)**. **M2 NOT started.** M2 requires: a decision on W2 (finish+commit, push as a WIP branch, or shelve), a clean tree, and explicit approval by the owner — or by Itay as acting owner (see below).
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

## Process changes from Advisor review #1 (2026-09-26)
- I-009 UI gate: before building any customer-facing screen, the worker sends the owner a one-sentence goal + a static mock. Wiring code starts only after the owner approves it.
- I-011 (refined by the owner): use a separate branch/worktree when there's parallel work, possible overlap or a clear isolation need. A single worker on an isolated task works on main with no extra overhead.
- Owner decisions (2026-09-26, after Advisor review #1):
  - I-007 split into 7a Semantic Search POC (first; small, measurable, real photos) and 7b the age-progression person POC (a separate worker/task);
  - I-008: a permanent evaluation library of 1–3k original photos with deliberate variety, growing to 5k/50k+;
  - I-010: PM #2 + Advisor on a cheaper model as an experiment, with decision quality measured.
  - I-012 APPROVED: research, an end-to-end UX comparison on the same real library (time, steps, quality, friction), not a feature list. I-013 APPROVED in principle, GATED on I-008. Metrics: time, cost, manual decisions, swaps, friction points, a ranked list of steps to automate.
  - **Next order (owner, final):**
    1. Exclusions #1 (M1 closes = the technical filter is stable enough to continue, NOT "photo selection solved").
    2. The owner builds the I-008 library + fills `evaluation/queries_template.md` (6 query types). The אחראי בקרת איכות תמונות #1 (Curation & Evaluation Lead) opens at the start of this step.
    3. Human ground truth (labels).
    4. A baseline curation measurement of the current filter.
    5. The 7a semantic-search POC, evaluated INSIDE the curation framework: does it improve curation?
    6. I-012 research.
    7. Advisor review.
    8. I-013 concierge album.
    9. The 7b people POC, and so on.
    The Curation Quality Track stays open and high-priority until the gate evidence exists.
- Tooling freeze until the I-007 spike runs (only I-002 is allowed, if it stays small).

## 7a POC decision (PM #1, 2026-09-26, from MODEL_REGISTRY `541108e`)
- Compare **SigLIP 2 base** (primary; Apache-2.0 weights, multilingual, Core ML path) against **OpenCLIP xlm-roberta-base-ViT-B-32** (multilingual baseline; POC_ONLY because of LAION provenance).
- Before downloading, the 7a worker must verify on the local machine (the cloud couldn't reach the sources): the license text of the code AND the weights on the official model cards, the Core ML/iPhone path, and the published speed. It updates MODEL_REGISTRY.
- Evaluation belongs to the curation lead: Hebrew + English queries from `evaluation/queries_template.md`, measured on the owner's seed / eval library. Winner by measured quality, speed per 1,000 photos, license and iPhone feasibility, never by demo.
- 7a starts only after the seed labels exist (ground truth first).

## Curation gate evidence (required before album generation depends on curation)
1. The evaluation set is real: ≥1,000 original photos covering several years, people, pets, trips, events and junk types, fully owner-labeled. Part of it is held out and never used for tuning.
2. False exclusion: the "definitely include" rate (target set from the baseline, expected to be very low) and **zero** lost "special moment" photos, measured at the candidate stage.
3. Candidate-stage recall for "definitely + probably include" is high enough that ranking gets nearly everything the owner wants.
4. Junk retention is measured, and trending down across rounds without hurting #2 and #3.
5. Duplicates: agreement with the owner's preferred copy.
6. Coverage of the requested people/events/years for 2–3 real album requests.
7. Each round shows measurable improvement over the previous baseline, and the results hold on the held-out part.
8. Owner blind review of the final selection for 2–3 real requests: acceptance rate plus the list of misses.
9. Runtime per 1,000 photos is within the M7 benchmark budget (current ingest baseline: ~51 s / 1,000 photos on synthetic data; the curation budget gets set in the baseline round).
10. Labels, per Advisor #1:
   - Request-INDEPENDENT labels on the full set: junk / duplicate + preferred copy / special moment / keep-worthy / technically poor but important.
   - Per-request relevance labels only for the 2–3 test requests.
11. (Owner, 2026-09-26: NO second labeler for now.) Instead, **AI-assisted ground truth**: the AI proposes labels/ratings, the owner confirms or corrects them in the existing web UI, and ONLY the owner-confirmed result is saved as the human label. AI proposals are stored separately and are never treated as truth.
   - אחראי בקרת איכות תמונות #1 must evaluate using the filter-review screen ("מה הסינון הציע?", review_labels) as the base for the labeling screen.
   - Guards against anchoring: show a random ~10% subset WITHOUT the AI suggestion, and compare the owner's labels there; report the owner's correction rate on AI proposals.
   - Owner refinements:
     - Separate OBJECTIVE labels (duplicate, screenshot/document, technical quality) from SUBJECTIVE ones (special moment, keep-worthy). For subjective labels the AI shows a suggestion + confidence, never a verdict.
     - Start with a SMALL set of critical labels only. No heavy tagging system up front: the goal is fast ground truth, not a labeling project.
   - Privacy: the AI that proposes labels runs LOCALLY by default. Sending photos to any external AI/vision service needs a separate explicit owner decision (guardrail).
12. Structural conservatism (ADR-021): verified by design.
Roles: the אחראי בקרת איכות תמונות #1 (Curation & Evaluation Lead) opens when the owner starts building the I-008 library (first deliverables: the eval plan, the library composition spec, the label schema, the query list template), then the baseline round on the current filter.

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
- **Attached (owner-approved I-004, 2026-09-26):** automatic DB backup before a schema-changing migration.
  - Back up ONLY when a migration will change the schema, never on a normal startup.
  - Retention: keep a bounded number, e.g. the last 5, and prune older ones.
  - If the backup fails, the migration does NOT run (the app stops with a clear error).
  - Log + document where the backup was saved and what happened.
  - Automated test: a failed backup → migration not applied, schema version unchanged.
  - If this expands W2's scope significantly, W2 stops and reports to the PM before continuing. The PM must include this in W2's resume message.
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
- Schema: v3 = W2 (committed e806743), v4 = W1 (committed). **v5 RESERVED for curation_labels + ai_label_proposals (Curation Lead #1 spec; implemented by עובד תיוג #1). Next free: v6.**
- ADR: 016 = W2 (uncommitted), 017 = W1, 018 = W1, 019 = W3 (dashboard), 020 = W4 (dev reload, committed), 021 = PM (technical flags demote, not exclude), 022 = curation labels (reserved). **Next free: ADR-023.**

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
