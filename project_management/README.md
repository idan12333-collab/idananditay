# Project-management dashboard ("control center")

A local-only, read-mostly dashboard that lets the (non-technical) owner see the
state of the AI Photo Album project in about a minute: what is done, who is
working on what, what is waiting for the owner, git state, roadmap and daily
summaries. Hebrew, RTL.

**This is dev tooling, not part of the photo-album product.** It lives entirely in
`project_management/` plus `start_project_manager.bat`.

## Run

- Double-click `start_project_manager.bat` → serves on <http://127.0.0.1:8790> and opens the browser.
- Or: `python -m project_management.server [--port 8790] [--no-browser]`
- Tests: `python -m pytest -p no:cacheprovider project_management/tests`

Python 3.12 standard library only (no new dependencies). The script uses the
project venv (`%USERPROFILE%\.ai-photo-album\venv`) if present, else `py -3.12`.

## What it can and cannot do

The dashboard **cannot control Claude sessions.** It only reads files, and it
writes prepared *requests* to `project_management/inbox.jsonl`. Every action button
produces a ready Hebrew message which the owner pastes into the Project Manager
session ("נשלח דרך המנהל — יש להדביק לו"). "Approve commit" approves nothing: it only
opens the worker's session, where approval is typed. There is no automatic
end-of-day summary; the "צור סיכום יום" button prepares a request for one.

The browser page polls its own local server every ~10 s. No other background
work, no external services, no CDN, no telemetry.

## Data sources

| Source | What for | Written by |
|---|---|---|
| git (read-only allowlist) | branch, last commits, dirty files | — |
| `ACTIVE_WORK.md` | live coordination (parsed leniently, raw fallback) | PM |
| `ROADMAP.md` | milestone progress from checkboxes | PM / workers |
| `DECISIONS.md` | ADR titles | PM / workers |
| `MEMORY.md` | "Current state" excerpt | PM / workers |
| `project_management/state.json` | what only the PM knows (schema below). **git-ignored** | PM |
| `project_management/daily/YYYY-MM-DD.md` | daily summaries. **committed** (docs-only commits) | PM |
| `project_management/inbox.jsonl` | requests from the dashboard. **git-ignored**, append-only | dashboard |
| `%USERPROFILE%\.claude\projects\<project>\*.jsonl` | optional: last activity, recent tool activity, *estimated* context | Claude Code |

If `state.json` is missing or unreadable the dashboard shows
"המנהל עוד לא עדכן מצב" plus everything git/docs can give.

## `state.json` schema (schema_version 1) — FROZEN 2026-09-26

The PM writes it atomically (temp file + rename). The dashboard reads defensively:
every field is optional; missing/invalid values fall back to defaults; unknown
worker statuses show as `UNKNOWN` (gray). See `state.example.json` for a full example.
Timestamps are ISO-8601 strings (with offset, e.g. `2026-09-26T15:20:00+03:00`).

```jsonc
{
  "schema_version": 1,
  "updated_at": "ISO",
  "pm": {
    "name": "project manager",
    "session_id": "local_…",
    "deep_link": "claude://…",            // only claude:// links are accepted
    "transcript_titles": ["project manager"],
    "owns": ["MEMORY.md", "ROADMAP.md", "DECISIONS.md", "ACTIVE_WORK.md", "CLAUDE.md", "project_management/daily/**"]
  },
  "overview_hebrew": "",                   // optional: strategic bird's-eye view, max ~3 short lines (
-separated).
                                           // Shown big at the top; falls back to project_summary.
  "project_summary": {                     // Hebrew, one short sentence each
    "completed": "", "active": "", "waiting": "", "blocked": "", "needs_owner": "", "next": ""
  },
  "workers": [{
    "id": "W1", "name": "עובד איכות",
    "session_id": "local_…", "deep_link": "claude://…",
    "transcript_titles": ["עובד איכות"],   // session titles (current + former) used to find its transcript
    "task": "", "status": "ACTIVE|WAITING|BLOCKED|DONE|PLANNED",
    "now_hebrew": "", "current_step": "",
    "done": [""], "remaining": [""],
    "owns": ["app/printing/**", "app/api/routes.py"],   // path globs; a file may have several owners
    "depends_on": ["W1"], "blocks": ["W2"],
    "start_commit": "7927635",
    "committed": false, "commit": null,    // commit = short hash once committed
    "tests": {"result": "passed|failed|not_run|null", "count": 84, "at": "ISO"},
    "manual_test": {"status": "not_needed|required|passed|failed", "steps": [""], "note": ""},
    "awaiting_owner_approval": false,
    "context": {"percent": 28, "source": "exact|estimate", "at": "ISO"},   // percent may be null
    "next_action": "",
    "last_update": {"text": "", "at": "ISO"}
  }],
  "tasks": [{
    "id": "T1", "title_hebrew": "", "owner": "W2|''",
    "status": "PLANNED|PENDING_PM|ACTIVE|WAITING|BLOCKED|DONE|CANCELLED",
    "depends_on": [], "created_at": "ISO", "milestone": "M2", "notes": ""
  }],
  "attention": [{                          // ONLY items that need the owner
    "id": "A1",
    "type": "manual_test|approval|permission|commit|product_decision|conflict|licensing_privacy",
    "text_hebrew": "", "worker": "W1", "how_to_act": "", "created_at": "ISO"
  }],
  "changes":   [{"at": "ISO", "text_hebrew": "", "worker": "W1"}],          // "מה השתנה לאחרונה"
  "completed": [{"at": "ISO", "text_hebrew": "", "milestone": "M1", "commit": "abc1234"}],  // never pruned
  "timeline":  [{"at": "ISO", "worker": "W1",
                 "event": "started|paused|finished|tests_passed|tests_failed|manual_test_requested|manual_test_passed|manual_test_failed|commit|resumed|handoff|conflict",
                 "text_hebrew": ""}],
  "plan_usage": {"five_hour_percent": 58, "five_hour_resets_at": "ISO", "weekly_percent": 15, "at": "ISO", "note": ""},  // optional
  "efficiency": {"recommendations_hebrew": [""], "at": "ISO"},   // optional (added 2026-09-26, additive)
  "roadmap_notes": {"M2": ["מה עוד חסר כדי להתקדם"]},             // optional (added 2026-09-26, additive).
                                           // Key = "M<number>", "<number>" or the milestone title from ROADMAP.md.
  "roadmap_titles_hebrew": {"M1": "סריקת תמונות"},  // optional (added 2026-09-26, additive): Hebrew milestone
                                           // names shown instead of the English ROADMAP.md headings (same keys).
  "inbox_handled": [12, 13]                // ids of inbox requests the PM has handled
}
```

### Context level

`context.percent` from the PM (`source: exact`) wins when it is newer than the
transcript estimate. Otherwise the dashboard *estimates* it from the worker's
transcript (last main-thread assistant message: `input + cache_creation + cache_read`
tokens ÷ 1,000,000) and labels it "הערכה". No usable data → no number is shown.
Levels: < 70 healthy · 70–85 getting high · 85–95 near limit (shows recommended
action: compact vs. fresh handoff) · ≥ 95 handoff recommended.

### Efficiency banner

There is no efficiency section (owner feedback 2026-09-26). The page shows one quiet
banner **only when something is actionable**: the short (5-hour) quota is ≥ 80 %
(from `plan_usage`; nothing is shown if it is missing — never an invented number),
the weekly quota is ≥ 80 %, or a worker's context is ≥ 70 %. The API still computes
the full `efficiency` block (counts, estimated turns/hour, rule-based recommendations,
`efficiency.recommendations_hebrew`) for the PM; the technical-details area lists it.

## Inbox (`inbox.jsonl`)

One JSON object per line: `{"id", "at", "type", "worker", "text", "status": "pending"}`.
The dashboard only appends. A request is shown as handled when its id is listed in
`state.json` → `inbox_handled`.
Types: `status_request, pause_worker, continue_worker, message_worker,
manual_test_passed, manual_test_failed, new_task, summarize, daily_summary, new_worker`.

## Security

- Binds `127.0.0.1` only; rejects any `Host` other than `127.0.0.1:<port>` / `localhost:<port>`.
- POST requires `Sec-Fetch-Site: same-origin|none`, a matching `Origin` if present, and `Content-Type: application/json`; body ≤ 16 KB.
- Static files only from `project_management/web/` (fixed list, no path traversal). No arbitrary file reads.
- No shell execution. git runs only from a fixed allowlist of read-only commands with fixed arguments (`shell=False`, `GIT_OPTIONAL_LOCKS=0` so it never takes the index lock other sessions use).
- `.env` and secret-looking files are never read or shown; text from transcripts/docs passes through a redaction filter.
- Transcript adapter: never emits thinking/reasoning, tool inputs or command text; only tool names, repo-relative paths, timestamps, test-result lines and short visible assistant text.
- Response headers: strict CSP (`default-src 'self'`), `nosniff`, `no-referrer`, `frame-ancestors 'none'`.

## ADR-019 — Local project-management dashboard (dev tooling)

**Status:** accepted (2026-09-26, owner approved via PM).

**Context.** Several Claude sessions (PM + workers) work in parallel on one working
tree. The owner is non-technical and needs a quick, trustworthy view of the state
without reading markdown files or chat transcripts.

**Decision.** A separate, stdlib-only local web dashboard in `project_management/`,
served on `127.0.0.1:8790` by `start_project_manager.bat`. It aggregates git (read-only
allowlist), the coordination docs, a PM-written `state.json` (git-ignored), PM-written
daily summaries (committed) and, optionally, Claude Code transcripts (read-only,
redacted, estimate-only context). Actions are honest *requests* appended to
`inbox.jsonl` for the owner to paste to the PM; the dashboard never controls sessions.

**Tradeoffs.** The PM must keep `state.json` current (the dashboard is only as fresh as
it is). The transcript format is undocumented, so that adapter is isolated in one
module and degrades to "no data". Hebrew-only UI.

**Reversible?** Yes — delete `project_management/` and the `.bat`; the product is untouched.
