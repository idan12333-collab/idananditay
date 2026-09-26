"""Load and normalize ``project_management/state.json`` (written by the PM session).

The file is git-ignored and may be missing, half-written or hand-edited. Every
field is normalized to a safe default so the dashboard never crashes on it.
Schema: see ``project_management/README.md`` (schema_version 1).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

WORKER_STATUSES = {"ACTIVE", "WAITING", "BLOCKED", "DONE", "PLANNED"}
TASK_STATUSES = {"PLANNED", "PENDING_PM", "ACTIVE", "WAITING", "BLOCKED", "DONE", "CANCELLED"}
MANUAL_TEST_STATUSES = {"not_needed", "required", "passed", "failed"}
TEST_RESULTS = {"passed", "failed", "not_run"}
CONTEXT_SOURCES = {"exact", "estimate"}
ATTENTION_TYPES = {
    "manual_test", "approval", "permission", "commit",
    "product_decision", "conflict", "licensing_privacy",
}
TIMELINE_EVENTS = {
    "started", "paused", "finished", "tests_passed", "tests_failed",
    "manual_test_requested", "manual_test_passed", "manual_test_failed",
    "commit", "resumed", "handoff", "conflict",
}
_DEEP_LINK_RE = re.compile(r"^claude://[A-Za-z0-9._~:/?#@!$&'()*+,;=%\-]+$")
_MAX_STR = 4000
_MAX_LIST = 500


# ---------------------------------------------------------------- primitives

def _str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        v = str(v)
    if not isinstance(v, str):
        return default
    return v[:_MAX_STR]


def _opt_str(v: Any) -> str | None:
    s = _str(v)
    return s or None


def _bool(v: Any) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() in {"true", "yes", "1"})


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip().rstrip("%"))
        except ValueError:
            return None
    return None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _str_list(v: Any) -> list[str]:
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    return [s for s in (_str(x) for x in v[:_MAX_LIST]) if s]


def _enum(v: Any, allowed: set[str], default: str, upper: bool = False) -> str:
    s = _str(v).strip()
    s = s.upper() if upper else s.lower() if s and not upper else s
    return s if s in allowed else default


def _dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _list_of(v: Any, fn) -> list:
    if not isinstance(v, list):
        return []
    out = []
    for item in v[:_MAX_LIST]:
        if isinstance(item, dict):
            out.append(fn(item))
    return out


def deep_link(v: Any) -> str | None:
    s = _str(v).strip()
    return s if s and _DEEP_LINK_RE.match(s) else None


# ---------------------------------------------------------------- records

def _worker(d: dict) -> dict:
    tests = _dict(d.get("tests"))
    manual = _dict(d.get("manual_test"))
    ctx = _dict(d.get("context"))
    last = _dict(d.get("last_update"))
    committed_raw = d.get("committed")
    commit = _opt_str(d.get("commit")) or (committed_raw if isinstance(committed_raw, str) and committed_raw.strip() else None)
    pct = _num(ctx.get("percent"))
    if pct is not None and not (0 <= pct <= 100):
        pct = None
    titles = _str_list(d.get("transcript_titles"))
    if not titles and _str(d.get("transcript_title")):
        titles = [_str(d.get("transcript_title"))]
    status_raw = _str(d.get("status")).strip().upper()
    return {
        "id": _str(d.get("id")) or _str(d.get("name")) or "?",
        "name": _str(d.get("name")) or _str(d.get("id")) or "עובד ללא שם",
        "session_id": _opt_str(d.get("session_id")),
        "deep_link": deep_link(d.get("deep_link")),
        "transcript_titles": titles,
        "task": _str(d.get("task")),
        "status": status_raw if status_raw in WORKER_STATUSES else "UNKNOWN",
        "now_hebrew": _str(d.get("now_hebrew")),
        "current_step": _str(d.get("current_step")),
        "done": _str_list(d.get("done")),
        "remaining": _str_list(d.get("remaining")),
        "owns": _str_list(d.get("owns")),
        "depends_on": _str_list(d.get("depends_on")),
        "blocks": _str_list(d.get("blocks")),
        "start_commit": _opt_str(d.get("start_commit")),
        "committed": bool(commit) or _bool(committed_raw),
        "commit": commit,
        "tests": {
            "result": _enum(tests.get("result"), TEST_RESULTS, "not_run") if tests.get("result") else None,
            "count": _int(tests.get("count")),
            "at": _opt_str(tests.get("at")),
        },
        "manual_test": {
            "status": _enum(manual.get("status"), MANUAL_TEST_STATUSES, "not_needed"),
            "steps": _str_list(manual.get("steps")),
            "note": _str(manual.get("note")),
        },
        "awaiting_owner_approval": _bool(d.get("awaiting_owner_approval")),
        "context": {
            "percent": pct,
            "source": _enum(ctx.get("source"), CONTEXT_SOURCES, "") or None if pct is not None else None,
            "at": _opt_str(ctx.get("at")),
        },
        "next_action": _str(d.get("next_action")),
        "last_update": {"text": _str(last.get("text")), "at": _opt_str(last.get("at"))},
    }


def _task(d: dict) -> dict:
    status_raw = _str(d.get("status")).strip().upper()
    return {
        "id": _str(d.get("id")) or "?",
        "title_hebrew": _str(d.get("title_hebrew")) or _str(d.get("title")),
        "owner": _str(d.get("owner")),
        "status": status_raw if status_raw in TASK_STATUSES else "PENDING_PM",
        "depends_on": _str_list(d.get("depends_on")),
        "created_at": _opt_str(d.get("created_at")),
        "milestone": _str(d.get("milestone")),
        "notes": _str(d.get("notes")),
    }


def _attention(d: dict) -> dict:
    return {
        "id": _str(d.get("id")),
        "type": _enum(d.get("type"), ATTENTION_TYPES, "approval"),
        "text_hebrew": _str(d.get("text_hebrew")),
        "worker": _str(d.get("worker")),
        "how_to_act": _str(d.get("how_to_act")),
        "created_at": _opt_str(d.get("created_at")),
    }


def _change(d: dict) -> dict:
    return {"at": _opt_str(d.get("at")), "text_hebrew": _str(d.get("text_hebrew")), "worker": _str(d.get("worker"))}


def _completed(d: dict) -> dict:
    return {
        "at": _opt_str(d.get("at")),
        "text_hebrew": _str(d.get("text_hebrew")),
        "milestone": _str(d.get("milestone")),
        "commit": _opt_str(d.get("commit")),
    }


def _timeline(d: dict) -> dict:
    ev = _str(d.get("event")).strip().lower()
    return {
        "at": _opt_str(d.get("at")),
        "worker": _str(d.get("worker")),
        "event": ev if ev in TIMELINE_EVENTS else "other",
        "text_hebrew": _str(d.get("text_hebrew")),
    }


def _summary(d: dict) -> dict:
    keys = ("completed", "active", "waiting", "blocked", "needs_owner", "next")
    return {k: _str(d.get(k)) for k in keys}


def _pm(d: dict) -> dict:
    return {
        "name": _str(d.get("name")) or "project manager",
        "session_id": _opt_str(d.get("session_id")),
        "deep_link": deep_link(d.get("deep_link")),
        "owns": _str_list(d.get("owns")),
        "transcript_titles": _str_list(d.get("transcript_titles")),
    }


def _plan_usage(v: Any) -> dict | None:
    if not isinstance(v, dict):
        return None
    return {
        "five_hour_percent": _num(v.get("five_hour_percent")),
        "five_hour_resets_at": _opt_str(v.get("five_hour_resets_at")),
        "weekly_percent": _num(v.get("weekly_percent")),
        "at": _opt_str(v.get("at")),
        "note": _str(v.get("note")),
    }


def _efficiency(v: Any) -> dict | None:
    if not isinstance(v, dict):
        return None
    return {"recommendations_hebrew": _str_list(v.get("recommendations_hebrew")), "at": _opt_str(v.get("at"))}


def _roadmap_notes(v: Any) -> dict[str, list[str]]:
    if not isinstance(v, dict):
        return {}
    out: dict[str, list[str]] = {}
    for k, notes in list(v.items())[:100]:
        key = _str(k).strip()
        if key:
            out[key] = _str_list(notes)
    return out


def _str_map(v: Any) -> dict[str, str]:
    if not isinstance(v, dict):
        return {}
    out = {}
    for k, val in list(v.items())[:100]:
        key, text = _str(k).strip(), _str(val).strip()
        if key and text:
            out[key] = text
    return out


def normalize(raw: Any) -> dict:
    d = _dict(raw)
    handled = d.get("inbox_handled")
    return {
        "schema_version": _int(d.get("schema_version")) or SCHEMA_VERSION,
        "updated_at": _opt_str(d.get("updated_at")),
        "pm": _pm(_dict(d.get("pm"))),
        "overview_hebrew": _str(d.get("overview_hebrew")),
        "project_summary": _summary(_dict(d.get("project_summary"))),
        "roadmap_notes": _roadmap_notes(d.get("roadmap_notes")),
        "roadmap_titles_hebrew": _str_map(d.get("roadmap_titles_hebrew")),
        "workers": _list_of(d.get("workers"), _worker),
        "tasks": _list_of(d.get("tasks"), _task),
        "attention": _list_of(d.get("attention"), _attention),
        "changes": _list_of(d.get("changes"), _change),
        "completed": _list_of(d.get("completed"), _completed),
        "timeline": _list_of(d.get("timeline"), _timeline),
        "plan_usage": _plan_usage(d.get("plan_usage")),
        "efficiency": _efficiency(d.get("efficiency")),
        "inbox_handled": [i for i in (_int(x) for x in handled) if i is not None] if isinstance(handled, list) else [],
    }


def load(path: Path) -> tuple[dict, str, str | None]:
    """Return ``(normalized_state, status, error)``; status is ok|missing|corrupt.

    Never raises. A half-written file (the PM writes atomically, but be safe)
    reads as ``corrupt`` and yields an empty normalized state.
    """
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return normalize({}), "missing", None
    except OSError as exc:
        return normalize({}), "corrupt", f"לא ניתן לקרוא את הקובץ: {exc.__class__.__name__}"
    try:
        raw = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return normalize({}), "corrupt", f"JSON לא תקין: {exc}"[:300]
    if not isinstance(raw, dict):
        return normalize({}), "corrupt", "הקובץ אינו אובייקט JSON"
    return normalize(raw), "ok", None
