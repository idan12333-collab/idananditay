# Worker Registry

A permanent audit record of every worker session. Numbers are never reused: each category counts #1, #2, … for the life of the project. This is history, not a transcript. Live coordination lives in ACTIVE_WORK.md.

Statuses:
- ACTIVE: currently working.
- WAITING: intentionally idle.
- DONE: completed its assigned work.
- RETIRED: closed on purpose because context or scope made continued use inefficient.
- REPLACED: replaced before completing its role.
- FAILED: the work couldn't safely continue.

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

## Cloud-worker rule (owner, 2026-09-26; permanent)
The Project Manager is the operational authority and coordination hub. Cloud workers stay synchronized with the PM on all meaningful work.
- Cloud workers never change priorities or roadmap direction on their own, never start unrelated work, never merge to `main`, never touch work reserved for another worker, and never create a parallel management process.
- If the PM is temporarily unavailable, a cloud worker continues only work that is already clearly within its approved scope.
- Conflicts, stale documentation, local-only dependencies, architecture/product risks and new ideas are raised to the PM, not decided silently.
- Every cloud task ends with a section **"Handoff to Project Manager"** covering: branch/commit; what changed; tests/research performed; assumptions; unresolved issues; dependencies/conflicts; recommended next action; what requires PM approval. The handoff is committed under `project_management/handoffs/` on the worker's branch.

## Registry

### Project Manager #1
- Session: "project manager" (`local_c0a790a5-b448-43eb-8131-d1b38c8cc58d`). Status: **ACTIVE**. Started: 2026-09-26 14:41.
- Scope: coordination, state files, the owner interface. No feature code.
- Handoff plan: before the Japan trip PM #1 writes a final handoff and becomes RETIRED; **Project Manager #2** starts on Itay's computer with the startup instruction in `HANDOFF_TO_ITAY.md`.

### Quality Worker #1 (session title "עובד איכות", formerly "איכות סינון תמונות")
- Session `local_a74829e2-41be-4774-904d-cb88a891e546`. Status: **DONE**. Started: 2026-09-26 ~13:00. Ended: 18:22. Start commit: `7927635`. End commit: `a9783bb`.
- Scope: print suitability (now internal), human review labels, the "מה הסינון הציע?" filter-review screen, the delete-library cleanup. Schema v4, ADR-017, ADR-018.
- Lessons:
  - three UX rounds, because the product goal was clarified late; next time, agree on the one-sentence goal before building UI;
  - peak context ~466k tokens made each step expensive;
  - repeated network (DNS) errors near the end.

### Exclusions Worker #1 (session title "עובד החרגות", formerly "החרגת תמונות בסינון")
- Session `local_028eae54-f07c-4076-8f47-8692a8134014`. Status: **WAITING**. Started: 2026-09-26 ~11:00. Start commit: `7927635`. Its uncommitted work exists ONLY on the owner's PC (not in GitHub) — needs an owner/PM decision before the Japan trip.
- Scope: pre-scan exclusions (schema v3, ADR-016). About 1/3 done, uncommitted, paused because of file overlap with Quality #1.
- Context 21%. It resumes after Dev Reload #1, per the owner's order.

### Dashboard Worker #1 (session title "Dashboard Worker")
- Session `local_e2492d03-fa5c-4973-943e-6e50128324d7`. Status: **DONE**. Started: 2026-09-26 15:05. Ended: 18:20. Start commit: `7927635`. End commit: `55b7761`.
- Scope: the local project-management dashboard (`project_management/`, `start_project_manager.bat`), ADR-019.
- Lessons: 61 requests in 25 minutes, with screenshot-heavy self-checks; it became the largest usage consumer after the reset.

### Dev Reload Worker #1
- Status: work committed as `64d099a` (ADR-020, 2026-09-26 18:52). Session id, final status (DONE/RETIRED) and lessons are not in Git — **PM to fill in locally**.
- Scope: dev auto-reload for the app and the dashboard (ADR-020).

### Cloud Handoff Worker #1 (cloud session, branch `claude/happy-cori-p2nejq`)
- Status: **DONE** (pending PM review). Started/ended: 2026-09-26. Start commit: `64d099a`.
- Scope: read-only audit, then `HANDOFF_TO_ITAY.md`, Git-verified fixes to the state docs, README "new machine" section, PM startup instruction. No product code, no W2, no local data.
- Deliverable for the PM: `project_management/handoffs/2026-09-26_cloud_handoff_for_pm.md`. Nothing merged to `main`.

## Roles not yet documented here (must be filled in locally)
The owner referred to a **Product & Efficiency Advisor** and an **Image Quality Control / Curation lead**. Neither role is described in any file in Git. PM #1 (or the owner) must add their scope, when they are used and their current status/number before the handoff; the cloud session did not invent them.
