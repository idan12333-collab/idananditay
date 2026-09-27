# Worker Registry

A permanent audit record of every worker session. Numbers are never reused: each category counts #1, #2, … for the life of the project. This is history, not a transcript. Live coordination lives in ACTIVE_WORK.md.

Statuses:
- ACTIVE: currently working.
- WAITING: intentionally idle.
- DONE: completed its assigned work.
- RETIRED: closed on purpose because context or scope made continued use inefficient.
- REPLACED: replaced before completing its role.
- FAILED: the work couldn't safely continue.

## Onboarding step 0: working folder (owner, 2026-09-26)
Before the interview, the PM checks the new session's cwd with list_sessions. It must be the project folder `C:\Users\idan1\OneDrive\שולחן העבודה\קלוד\אלבום`, OR — for a worker deliberately isolated in a worktree (I-011) — the exact worktree path the PM created for it. If it isn't there yet, the PM's first message tells the worker to switch to that folder itself (the change_directory tool). If the worker can't switch, the PM tells the owner the single action: "reopen the session in the project folder". The owner doesn't need to remember any of this.

**Mandatory last step of EVERY onboarding, no exceptions (owner-flagged 2026-09-26, a real miss on Quality Worker #2 — the owner should never have to remind the PM):** immediately after renaming the session to its worker title — in the SAME batch of tool calls, before sending any brief or task content — the PM calls `ccd_sidebar move_sessions` to file it into "אלבום · פעילים". This is not conditional on remembering it later; it is step 3 of onboarding (see the numbered sequence below), done mechanically every time, worktree or not.

**The fixed onboarding sequence (do all of these, in order, every time):**
1. Verify/fix cwd (step 0 above).
2. Rename the session to its worker title (`set_session_title`).
3. File it into "אלבום · פעילים" (`ccd_sidebar move_sessions`) — right here, not deferred.
4. Send the brief / start the interview.
5. Update WORKERS.md (register the worker) and ACTIVE_WORK.md (status) — commit if the change is doc-only.

## Onboarding rule (owner, 2026-09-26)
Before a new worker gets implementation responsibility, it must answer, in one concise exchange:
1. What the task is.
2. The files/subsystems it expects to touch.
3. What it must not touch.
4. What "done" means.
5. Its test plan.
6. Possible conflicts with active work.
7. How it will limit context growth, repeated reads, screenshots, tests and tool calls.
8. When it will stop and ask instead of guessing.

The PM corrects any misunderstanding before coding starts. A worker that can't explain the task clearly doesn't start.

Standing efficiency rules for every worker:
- read only the files the task needs, and don't reread the full project docs;
- no polling;
- batch edits;
- targeted tests while building, the full suite at checkpoints;
- minimal visual checks;
- concise reports to the PM;
- don't expand scope: log unrelated issues as follow-ups;
- reach clean checkpoints before the context grows large.

## New-session rule (owner, 2026-09-26)
When a new worker is needed, the PM tells the owner ONLY the exact session name to create (e.g. "Dev Reload Worker #1"). Once the owner confirms it's open, the PM handles everything else over inter-session messaging: onboarding, the interview, the brief and coordination. The owner never prepares prompts or transfers context.

## Permanent role: Product & Efficiency Advisor (owner, 2026-09-26; autonomous PM↔Advisor pair)
- Roles:
  - Owner = product decisions.
  - PM = execution, coordination, roadmap control, workers, Git, blockers, delivery.
  - Advisor = an independent high-level challenge: product/business/workflow/efficiency ideas, risks/opportunities.
  - Workers = implementation.
- The Advisor NEVER implements, never assigns workers, never commits product code, never changes strategy or milestone order, and never makes irreversible decisions. The only file it may write is **IDEAS.md**.
- **Activation (event-driven, no polling):** the PM wakes the Advisor with a message containing a concise snapshot reference at these triggers:
  - milestone completed;
  - ~3+ meaningful commits since the last review;
  - a major owner test/feedback round;
  - a major bug/root cause or recurring friction;
  - a worker replacement that exposes an efficiency issue;
  - a material roadmap change;
  - before starting a new milestone;
  - a new daily summary with meaningful changes;
  - whenever the PM wants a second opinion.

  While the Advisor is awake, it may contact the PM on its own. Technical limit: an idle session can't wake itself, so "autonomous" means the PM triggers it automatically. The owner never has to.
- Snapshot only: ROADMAP, ACTIVE_WORK, MEMORY, DECISIONS, PROJECT_SPEC, WORKERS, IDEAS, `git log --oneline -15`, `git status --short`, the latest daily summary. No worker transcripts without a specific reason.
- Core questions:
  - manual work to automate;
  - accepted friction;
  - customer-experience gains;
  - ignored business risk;
  - expensive future problems to prevent now;
  - cheap validation before a big feature;
  - drift from the vision;
  - a simpler or more scalable way.
- Output: 1–5 strong ideas, each with: idea / problem / value H-M-L / effort S-M-L / timing / roadmap impact / owner / new worker needed? No duplicates of IDEAS.md entries.
- The Advisor may challenge the PM directly (overcomplication, inefficiency, premature features, missing capabilities, drift). The PM evaluates suggestions against the milestone, risk, effort, dependencies, usage and the vision, and doesn't accept them automatically.
- Joint classification: DO NOW / ATTACH TO CURRENT WORK / ROADMAP / BACKLOG / REJECT.
- **The owner is involved ONLY for product-owner decisions:** major scope, roadmap reorder, meaningful architecture, privacy/data-sharing/external services, business model, significant cost, removal of a planned capability, other strategic tradeoffs. Then the PM sends a short Hebrew decision brief: the proposal / why / the Advisor's position / the PM's position / cost-risk / options with a recommendation / the decision needed. Everything routine is handled without the owner.
- Efficiency: concise messages, no chatter, idle between reviews.

## Session archive rule (owner, 2026-09-26)
- WORKERS.md is the canonical history. The Claude sidebar is only for visual organization.
- The PM moves sessions itself using the sidebar tools. The groups:
  - "אלבום · פעילים" (current PM, current Advisor, active workers);
  - "אלבום · ממתינים" (WAITING workers);
  - "אלבום · הסתיימו (ארכיון)" (DONE / RETIRED / REPLACED / FAILED).
- On every status change: update WORKERS.md (final status, end commit, replacement, handoff) → move the session to the right group. Replacements keep their numbering (#1 archived → #2 active).
- If the move tool is unavailable, the PM tells the owner the exact single UI action.
- **Real miss, caught by the owner (2026-09-27):** the PM had let the sidebar drift — a WAITING worker (עובד החרגות #1) sat in the archive as if done, and several WAITING workers (labeling, curation lead, advisor) sat in "פעילים" as if working. The rule above was never wrong; it just wasn't run consistently. Treat "update the sidebar group" as inseparable from "update the status field" — the ACTIVE_WORK.md/WORKERS.md edit and the sidebar move happen in the same turn, never one without the other. When touching ANY worker's status line, re-check its sidebar group in the same turn even if that worker wasn't the reason for the edit.

## Cloud-worker rule (owner, 2026-09-26; permanent)
The Project Manager is the operational authority and coordination hub. Cloud workers stay synchronized with the PM on all meaningful work.
- Cloud workers never change priorities or roadmap direction on their own, never start unrelated work, never merge to `main`, never touch work reserved for another worker, and never create a parallel management process.
- If the PM is temporarily unavailable, a cloud worker continues only work that is already clearly within its approved scope.
- Conflicts, stale documentation, local-only dependencies, architecture/product risks and new ideas are raised to the PM, not decided silently.
- Every cloud task ends with a section **"Handoff to Project Manager"** covering: branch/commit; what changed; tests/research performed; assumptions; unresolved issues; dependencies/conflicts; recommended next action; what requires PM approval. The handoff is committed under `project_management/handoffs/` on the worker's branch.

## Registry

### Project Manager #1
- Session: "project manager" (`local_c0a790a5-b448-43eb-8131-d1b38c8cc58d`). Status: **REPLACED** (2026-09-26 ~23:15). Started: 2026-09-26 14:41.
- Scope: coordination, state files, the owner interface. No feature code.
- Reason for replacement: context reached ~540k and made it the biggest usage consumer (owner-approved). Handoff: ACTIVE_WORK.md "PM HANDOFF".

### Project Manager #2
- Session: "מנהל פרוייקט #2" (`local_ae3d6b14-31cd-4284-a516-321e510e7a64`). Status: **ACTIVE**. Started: 2026-09-26 23:10, on Idan's computer.
- Scope: same as PM #1. Itay becomes acting owner from Monday 2026-09-28 (`HANDOFF_TO_ITAY.md`).

### Quality Worker #1 (session title "עובד איכות", formerly "איכות סינון תמונות")
- Session `local_a74829e2-41be-4774-904d-cb88a891e546`. Status: **DONE**. Started: 2026-09-26 ~13:00. Ended: 18:22. Start commit: `7927635`. End commit: `a9783bb`.
- Scope: print suitability (now internal), human review labels, the "מה הסינון הציע?" filter-review screen, the delete-library cleanup. Schema v4, ADR-017, ADR-018.
- Lessons:
  - three UX rounds, because the product goal was clarified late; next time, agree on the one-sentence goal before building UI;
  - peak context ~466k tokens made each step expensive;
  - repeated network (DNS) errors near the end.

### Exclusions Worker #1 (session title "עובד החרגות", formerly "החרגת תמונות בסינון")
- Session `local_028eae54-f07c-4076-8f47-8692a8134014`. Status: **DONE** (end commit `e806743`, 2026-09-26 22:45). Started: 2026-09-26 ~11:00. Start commit: `7927635`. Its uncommitted work exists ONLY on the owner's PC (not in GitHub) — needs an owner/PM decision before the Japan trip.
- Scope: pre-scan exclusions (schema v3, ADR-016). About 1/3 done, uncommitted, paused because of file overlap with Quality #1.
- Context 21%. It resumes after Dev Reload #1, per the owner's order.

### Dashboard Worker #1 (session title "Dashboard Worker")
- Session `local_e2492d03-fa5c-4973-943e-6e50128324d7`. Status: **DONE**. Started: 2026-09-26 15:05. Ended: 18:20. Start commit: `7927635`. End commit: `55b7761`.
- Scope: the local project-management dashboard (`project_management/`, `start_project_manager.bat`), ADR-019.
- Lessons: 61 requests in 25 minutes, with screenshot-heavy self-checks; it became the largest usage consumer after the reset.

### Dev Reload Worker #1
- Session `local_189577cd-a15a-49da-bdda-9894d42ec89f` (titled "#1 עובד רענון דשבורדים אוטומטי"). Status: **DONE**. Started: 2026-09-26 18:40. Ended: ~19:00. Start commit: `6a7a1eb`. End commit: `64d099a`. Passed its onboarding interview in one exchange. Lesson: on Windows the venv python.exe is a launcher; the process-tree kill + a per-launch dev_instance token were needed to avoid a stale server.
- Scope: dev auto-reload for the app and the dashboard (ADR-020). The onboarding interview is required before any code.

### Product & Efficiency Advisor #1
- Session `local_3c7e1461-6729-4dfa-98a4-093b841f08c4` (titled "יועץ מוצר ויעילות #1"). Status: **WAITING** (idle). Started: 2026-09-26 ~19:05. Passed its onboarding interview in one exchange and confirmed it's an advisor, not an implementer. First review is scheduled after the quota reset (trigger 22:17).

### אחראי בקרת איכות תמונות #1 (Curation & Evaluation Lead)
- Session `local_eaba79d0-7816-4b66-a367-b722a7ed936c`. Status: **ACTIVE**. Started: 2026-09-26 ~23:10. Passed its onboarding interview (it had already checked its cwd). First deliverable: the owner's pre-trip labeled SEED (a few hundred photos), then EVAL_PLAN / LIBRARY_SPEC / LABEL_SCHEMA / queries / the baseline.
- Scope: owns curation quality + the evaluation methodology. Defines tests, compares approaches, measures, finds failure modes; coordinates implementation through the PM. Plan: see ACTIVE_WORK "Curation gate evidence" (AI-assisted ground truth, objective vs. subjective labels with confidence, a small label set, a 10% blind subset, local by default).

### Cloud Worker #1 (cloud session titled "פרויקט ביקורת ענן"; formerly logged as "Cloud Handoff Worker #1")
- **Category:** Cloud Workers. It is managed by the PM like any other worker.
- **Communication:** the PM can't reach cloud sessions directly. The owner relays messages word for word: the PM writes the exact message → the owner pastes it → the owner pastes back the reply or handoff. The owner doesn't decide tasks.
- **Status:** WAITING (no task). Task 3, the M2 model shortlist, is DONE: branch `claude/cw1-m2-model-shortlist` merged by the PM as `541108e`. The PM decides any future research.
- Task I-014 + I-012: DONE, branch `claude/cw1-build-vs-buy` merged by the PM as `b6f8b49`.
- **History:**
  1. Handoff-to-Itay docs, branch `claude/happy-cori-p2nejq`. Merged by PM #1 as `cd87ca9`, DONE.
  2. I-012 desk research. Not in Git yet; the PM asked where it is.
- **Current task:** I-014 Build-vs-Buy / White-Label research. Brief: `project_management/handoffs/cloud_task_build_vs_buy.md` (commit `94f43f6`).
- **Branch/PR:** a new branch per task, never main. The PM reviews and merges.
- **Dependencies:** none. Research only, no overlap with local workers.
- **Last handoff:** `project_management/handoffs/2026-09-26_cloud_handoff_for_pm.md`.
- **Next action:** the owner relays the PM's message → Cloud Worker #1 runs I-014 → its handoff returns via the owner → the PM reviews and decides the next step.
- **Who performs the communication:** the owner (relay only).

### עובד תיוג #1 (Labeling Worker)
- Status: **DONE** — committed as `8454783` (schema v5, ADR-022). Owner labeled 220 real photos, re-test approved 2026-09-27.

### 7a POC Worker #1
- Session: "7a POC Worker #1" (`local_e97680e0-4761-4d15-9cbc-064e0d420576`). Mode: auto. Started: 2026-09-27 ~08:43.
- Scope: verify SigLIP 2 base's and OpenCLIP xlm-roberta-base-ViT-B-32's licenses independently (official model cards, not the MODEL_REGISTRY summary), confirm Core ML/iPhone path + speed claims, update MODEL_REGISTRY.md. Then run both against the owner's real library, evaluated via Curation Lead #1's framework (evaluation/queries_template.md), never by demo. No app code/schema change expected at this stage.
- Depends on: nothing (research + standalone eval script). Gates satisfied: round-0 baseline done, seed labels exist, tree clean.
