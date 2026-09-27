# Active Work — live coordination board

Source-of-truth split: **Git** = code state · **MEMORY.md** = project state · **ACTIVE_WORK.md** = live multi-session coordination.
Maintained by the Project Manager (PM) session. Workers: read this before touching code; message the PM on every status change.
Last updated: 2026-09-27 ~13:00 (PM #3).

**Restructuring note (PM #3, 2026-09-27, on the Efficiency & Sessions Lead's confirmed recommendation):** this file had grown to 279 lines / 54.6KB — ~58% of the four core coordination docs' combined weight, almost entirely full narrative history for workers already DONE, superseded rule drafts, and old handoff prose. Full verbatim history moved to `project_management/archive/active_work_history.md` — nothing deleted, read it only when you need the "why" behind a past decision. This file now holds only what's live.

## Handoff template (use for every future PM handoff — keep it under ~20 lines; fixed fields scan faster than prose and don't bury routing info)
- Why handing off / context %:
- Git state: HEAD hash, pushed?, uncommitted files and whose they are:
- Active workers (one line each: name, session id, one-line status, next step):
- Waiting workers (one line each):
- Open blockers:
- Next action:
- Do NOT do without the owner's approval:

## מצב נוכחי (current state — read this for day-to-day work, not the archive)
- **PM:** מנהל פרוייקט #3 (`local_f095085c-5fbd-414e-b807-f000d4326c2a`), ACTIVE since 2026-09-27 ~12:05.
- **Acting owner:** Idan traveling; **Itay is temporary full owner from 2026-09-28** (`HANDOFF_TO_ITAY.md`). Owner communication style: simple Hebrew, short, ask only real questions, state exactly which session to open.
- **Milestones:** M0 + M1 complete. **M2 (semantic search) ACTIVE** — 7a POC below.
- **Active workers:**
  - **7a POC Worker #1** (`local_e97680e0-...`): licenses verified in MODEL_REGISTRY.md. First report (`poc_7a_2026-09-27.md`) was a 12-photo dry run, not real — that run was then LOST when its session closed mid-run. Recovered: added disk logging + per-model partial-report checkpointing + embedding cache so a session drop can't lose completed work again; `evaluation/poc_7a_semantic_search.py` committed as `da36904` (Curation Lead imports `build_model`/`embed_images`/`embed_text` from it — signatures unchanged). Full 231-photo, both-model run in progress again now (`evaluation/reports/local/poc_7a_run.log`), currently slower than expected because it's CPU-competing with Curation Lead's embedding job on the same machine — both legitimately running, not stuck.
  - **אחראי בקרת איכות תמונות** (Curation & Evaluation Lead, `local_eaba79d0-...`): `queries_template.md` marked SUPERSEDED by the owner's `queries_template_researched.md`; `EVAL_PLAN.md` has a new "Retrieval rounds" (R1–R6) section. Building `evaluation/retrieval_eval.py` (3 owner-facing pages: query choice / must-find-by-date / pooled grading, plus a scorer) + `evaluation/retrieval_candidates.json` (25 candidate queries). Computing embeddings now. **Told to message the owner directly for page 1 (query choice)** — he had not seen a request from her as of 2026-09-27 ~13:15.
  - **אחראי יעילות וסשנים #1** (`local_de2166e2-...`): active internal auditor, see WORKERS.md "Role boundary" note. Just delivered its first PM-handoff-cost review (see below); measured file sizes, confirmed the restructuring direction, recommended a fixed short handoff template (adopted above).
- **Waiting (idle):**
  - **יועץ מוצר ויעילות #1** (`local_3c7e1461-...`): due for a review pass once 7a's real result lands.
  - **Cloud Worker #1** ("פרויקט ביקורת ענן"): no task; owner relays messages, can't be messaged directly.
- **Open blockers:** none blocking right now.
- **Next action:** 7a's real 231-photo run finishes → Curation Lead evaluates it in the retrieval framework → Advisor review → I-012 research → I-013 concierge album (gated) → 7b people POC.
- **Don't do without the owner's explicit approval:** start new implementation beyond what's already approved above.

## Standing rules (still active; full rationale/history in the archive)
- **Coordination:** every worker messages the current PM on finish / blocked / handoff / test-failure-affecting-another-worker / about-to-commit, with test result + exact file/hunk list + manual-test steps. A worker checks `git status` + this file before starting, confirms no scope overlap with an ACTIVE row. Commit gate: full suite green → owner (or Itay) validates manually → owner approves (in the worker's session, or to the PM who relays the exact words) → worker commits only its own hunks → verifies the staged tree in isolation (`git stash --keep-index` + full suite) → reports the hash. PM checks each worker's context via get_usage before assigning work: ≥70% no new large task, ≥85% checkpoint and hand off (notes here + in MEMORY.md). The PM hands itself off the same way.
- **Traffic-control philosophy (Efficiency Control v2):** maximize useful progress per unit of usage AND time — never minimize worker count for its own sake. Parallel workers are fine when scopes are truly independent (no shared files/schema/UI) and each has good ROI. Never a blanket slowdown for one expensive session — diagnose that session specifically. High consumption while shipping something real is fine; high consumption from polling/status chatter/redundant re-reads/browser loops is not.
- **PM efficiency discipline:** batch documentation commits at real checkpoints, not one per tiny edit. No polling, ever. Targeted reads/tests during work; full suite and full-doc reads only at real checkpoints. Hand off to the next PM at a natural clean checkpoint, not a fixed percentage.
- **I-009 UI gate:** before building any customer-facing screen, send the owner a one-sentence goal + a static mock; wiring starts only after approval.
- **I-011 isolation:** a separate branch/worktree only for genuine parallel-work/overlap risk; a single worker on an isolated task works on `main`.
- **Onboarding / worker lifecycle:** see WORKERS.md (fixed onboarding sequence, sidebar-archive rule, Advisor protocol, Cloud-worker rule).
- **Role boundary (Efficiency & Sessions Lead vs. Product & Efficiency Advisor):** see WORKERS.md "Role boundary" section — HOW-we-work token/session cost vs. WHAT-we-build product ROI. Decided by PM #3, 2026-09-27, owner-requested.
- **Curation gate evidence** (required before album generation depends on curation; full owner discussion in the archive): a real ≥1,000-photo labeled eval set with a held-out portion never used for tuning; zero lost "special moment" photos at the candidate stage; high candidate-stage recall for definitely/probably-include; junk retention measured and trending down without hurting recall; duplicate agreement with the owner's preferred copy; coverage of requested people/events/years for 2–3 real album requests; measurable round-over-round improvement holding on held-out data; owner blind review + acceptance rate + miss list; runtime budget per 1,000 photos; **AI-assisted ground truth only** — the AI proposes, the owner confirms/corrects, only the owner-confirmed result is truth, proposals stored separately, a blind ~10% subset guards against anchoring, local-only by default (any external vision API needs a separate explicit owner decision).
- **Real incident worth remembering:** creating a "new library" for an already-indexed folder (instead of rescanning) renumbers every photo/group ID and can orphan ID-keyed data — always rescan, never re-add.

## Settled product principles (already baked into the product; full owner discussion in the archive)
- Album relevance target = people and animals; everything else (landscapes, objects, screenshots) is judged later by the album request + semantic signals (M2+), never by the rule-based technical filter.
- Print size/PPI is invisible to the customer — internal-only, automatic layout decisions later.
- The technical filter uses neutral wording only ("פחות מתאימה כרגע לאלבום"), never "not a memory" — relevance judgments belong to the semantic layer, not the technical one.
- No photo is ever silently lost: everything flagged is de-prioritized, reviewable, and restorable — never deleted.

## Reservations (next free — full history in the archive)
- Schema: next free **v6**.
- ADR: next free **ADR-024**.

## Backlog (unassigned, not started)
- UI: jump directly to a specific photo by ID/filename during review, instead of only browsing.
- Calibrate quality thresholds on a real library (do before/with M2).
- HEIC decoder licensing (pillow-heif = POC_ONLY).
- `httpx` TestClient deprecation warning.
- Duplicate file `PRINT_INTEGRATION (1).md` (owner may delete it).

## Scheduled triggers (only the still-live one; fired one-shots moved to the archive)
| Trigger | Mechanism | Fires | Action | Must stay alive | If it fails |
|---|---|---|---|---|---|
| 24/7 autonomous operation, every 5h | `mcp__scheduled-tasks` task `album-pm2-overnight` (self-rescheduling one-shot, file: `C:\Users\idan1\.claude\scheduled-tasks\album-pm2-overnight\SKILL.md`) | every 5h, from 2026-09-27 03:15 Israel time, ongoing | Check every active/waiting worker, advance whatever the protocol allows without owner judgment, push pending doc commits, append one factual entry to `project_management/PM2_AUTONOMOUS_LOG.md`, reschedule its own next run +5h | Claude desktop app open at some point per interval (catches up on next launch) | Silent stop if the reschedule step itself fails — check `list_scheduled_tasks`/the Scheduled sidebar if progress stalls well past 5h |
| Worker finishes / network error | The worker reports + a one-shot `notify_when_idle` | On idle | Verify → next step, or resend "continue" if it died on an API/network error | Same | Owner flags a worker that looks stuck |

## Dependencies right now
- Curation Lead's `evaluation/retrieval_eval.py` imports `build_model`/`embed_images`/`embed_text` read-only from 7a's `poc_7a_semantic_search.py` (committed `da36904`) — 7a must not rename those signatures without telling Curation Lead first.
