# Cloud handoff → Project Manager review (2026-09-26)

From: Cloud Handoff Worker #1 (cloud session, branch `claude/happy-cori-p2nejq`, based on `main` = `64d099a`).
To: Project Manager #1 (local), and the next PM.
Status: **proposal for review. Nothing is merged to `main`.** The PM approves, rejects or modifies it before merging.

## Owner instruction behind this work
The owner (Idan) is going to Japan. **Itay is the temporary full project owner**: he approves commits, opens/closes workers, changes priorities, approves milestone progression, makes implementation/product decisions, accepts/rejects Advisor recommendations and continues the roadmap. The owner asked the cloud session to:
1. draft `HANDOFF_TO_ITAY.md`;
2. fix the stale state docs where Git proves the fix;
3. add a "new machine" section to the README;
4. add the PM startup instruction;
5. prepare this note.

Constraints: no product code, no W2, no invented local state, no merge to `main`.

## What changed (docs only)
| File | Change |
|---|---|
| `HANDOFF_TO_ITAY.md` (new, Hebrew) | Operating model with Itay as acting owner, setup pointer, the PM #2 startup instruction, the worker/Advisor/cloud model, the Git rules, the local-data inventory, recovery scenarios, the pre-trip checklist, and "[למילוי מקומי]" placeholders |
| `CLAUDE.md` | New rule 1b: Itay is the acting owner; a new PM starts with the instruction in HANDOFF |
| `README.md` | New section "New machine setup" (Windows, ~15 min) |
| `MEMORY.md` | New "Acting owner" section; a Git-verified state bullet (remote, HEAD, commit list); stale "uncommitted / do NOT commit" bullets relabelled as history (`a9783bb`); cloud test result; schema version 2 → 4 (verified in `app/db/database.py`); "no remote" fixed; next action allows Itay's approval |
| `ACTIVE_WORK.md` | Snapshot (remote, HEAD, only W2 uncommitted); new "Acting owner during the Japan trip" section; commit gate mentions Itay; W1 → DONE `a9783bb`; W3 → DONE `55b7761`; W4 → committed `64d099a`; dependencies updated; reservations: ADR-020 taken, **next free ADR-021**; the rule-1a backlog item → committed `6a7a1eb` |
| `WORKERS.md` | New permanent "Cloud-worker rule" (owner, mid-task instruction; PM = coordination hub, required handoff format); Dev Reload Worker #1 → work committed `64d099a` (final status for the PM to fill in); W2 marked local-only; a PM #1 → #2 handoff line; a Cloud Handoff Worker #1 entry; a "Roles not yet documented" section (Advisor, Curation lead) |
| `ROADMAP.md` | M1 header → closed (except W2); filter-review item checked (`a9783bb`); pre-scan exclusions marked unblocked + local-only |
| `project_management/handoffs/` (new folder) | This note |

Every factual correction is backed by `git log` or the code. No historical text was deleted, only relabelled.

## Needs local verification / completion (the cloud cannot see these)
1. **W2:** the real state of the uncommitted exclusions work, and the owner's decision (finish+commit / push `wip/exclusions` / shelve and release schema v3 + ADR-016).
2. **Unpushed local changes:** run `git status` and `git log origin/main..main` on the owner's PC. If the local docs changed after `64d099a`, merge them with this branch; local facts win.
3. **Advisor and Image Quality Control / Curation lead roles:** not in any Git file. Describe them in `WORKERS.md`.
4. **Dev Reload Worker #1:** session id, final status, lessons.
5. **Test results:** the cloud run (Linux, Py 3.11) was 88 passed / 9 skipped / 2 failed (`tests/test_dev_reload.py::test_restart_replaces_the_old_process`, `::test_old_process_never_keeps_serving_when_new_one_fails_to_bind`); `project_management/tests` 43 passed. Please confirm the full suite is green on Windows/Py 3.12. The docs changes can't affect tests.
6. **The owner's list of "notify Idan" topics** in HANDOFF section 2 is a *proposal*. The owner should confirm or cut it.
7. **The pinned "auto" mode requirement** for cross-session messaging on Itay's machine: confirm it still applies.

## What must happen before Japan (owner + PM)
- Decide on W2 and carry out the decision through Git.
- Private repo; Itay as Collaborator (Write); Itay's own Claude account connected to GitHub.
- The PM reviews and merges this branch (or a corrected version), then pushes.
- Fill in the "[למילוי מקומי]" items in HANDOFF, plus the two roles in WORKERS.md.
- PM #1 writes its final handoff, becomes RETIRED, pushes; the owner's tree is clean.
- A real setup rehearsal on Itay's machine (README section, then HANDOFF section 4).

## Needs the owner's (Idan's) approval
- The W2 decision.
- Whether any personal data (DB with labels, photos) goes to Itay, and how (encrypted drive only).
- Confirm or edit the proposed "notify Idan" list.
- Optional: branch protection on `main` (block force-push/deletion only); CI with GitHub Actions (Windows runner minutes cost).

## Can be automated later (on approval)
- CI: a GitHub Actions workflow on `windows-latest` + Python 3.12 running both test suites.
- A setup-check script for a new machine (Python 3.12, venv, ports, tests; Hebrew messages).
- A local-data inventory script (sizes/counts under `%USERPROFILE%\.ai-photo-album`, no content).
- Cloud workers for M2 license research (`MODEL_REGISTRY.md`) and print-provider research (`PRINT_INTEGRATION.md`); they need no photos.

## Not done on purpose
No product code, no W2 files, no local data assumptions, no new management layer, no PR, no merge. `PRINT_INTEGRATION (1).md` (a duplicate) is left for the owner to delete.

## Handoff to Project Manager
- **Branch/commit:** `claude/happy-cori-p2nejq` (pushed; the commit hash is in `git log origin/claude/happy-cori-p2nejq -1`), based on `main` = `64d099a`. Not merged.
- **What changed:** docs only; see the table "What changed" above.
- **Tests/research performed:**
  - read-only audit of the state docs vs `git log`;
  - checked `SCHEMA_VERSION` in `app/db/database.py`;
  - full suite in the cloud (Linux, Py 3.11): 88 passed / 9 skipped / 2 failed (dev_reload); dashboard suite: 43 passed.

  No product code was touched, so no new tests.
- **Assumptions:**
  - the local docs have not changed after `64d099a`;
  - W4's commit implies its work passed the commit gate;
  - Itay uses Windows;
  - "auto" mode is still the session convention.
- **Unresolved issues:** see "Needs local verification". The main ones:
  - the W2 decision;
  - the Advisor and Curation lead roles are undocumented;
  - the 2 dev_reload failures on Linux;
  - the "notify Idan" list is unconfirmed.
- **Dependencies/conflicts:**
  - touches the PM-owned docs (MEMORY, ACTIVE_WORK, WORKERS, ROADMAP) and CLAUDE.md. If the PM edited them locally, merge by hand, and local facts win;
  - no overlap with W2's files.
- **Recommended next action:** the PM reviews this branch on the owner's PC → fills in the "[למילוי מקומי]" items → merges into `main` and pushes → the owner decides on W2 → setup rehearsal with Itay.
- **Requires PM approval:**
  - merging any of this;
  - the wording of the acting-owner rule in CLAUDE.md/ACTIVE_WORK;
  - the new `project_management/handoffs/` convention;
  - registering Cloud Handoff Worker #1 in WORKERS.md.
