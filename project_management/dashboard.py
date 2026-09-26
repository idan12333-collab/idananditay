"""Aggregate every source into the single JSON document the page renders.

Each source is isolated: an error in one becomes an ``errors`` entry, never a crash.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .sources import daily, docs, gitinfo, inbox, owners, state
from .sources.transcripts import TranscriptReader, default_transcripts_dir

LEVELS = ((95, "handoff"), (85, "near"), (70, "high"), (0, "healthy"))


def parse_ts(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        t = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()   # naive → local time


def context_level(pct: float | None) -> str | None:
    if pct is None:
        return None
    for floor, name in LEVELS:
        if pct >= floor:
            return name
    return "healthy"


def resolve_context(pm_ctx: dict, estimate: dict | None) -> dict:
    """PM value (exact) wins when it is at least as new as the transcript estimate."""
    pm_pct, pm_at = pm_ctx.get("percent"), parse_ts(pm_ctx.get("at"))
    est_pct = estimate.get("percent") if estimate else None
    est_at = parse_ts(estimate.get("at")) if estimate else None
    use_pm = pm_pct is not None and (est_pct is None or est_at is None or (pm_at is not None and pm_at >= est_at))
    if use_pm:
        pct, source, at = pm_pct, pm_ctx.get("source") or "exact", pm_ctx.get("at")
    elif est_pct is not None:
        pct, source, at = est_pct, "estimate", estimate.get("at")
    else:
        pct = source = at = None
    return {"percent": pct, "source": source, "at": at, "level": context_level(pct)}


def _latest(*values: str | None) -> str | None:
    best, best_t = None, None
    for v in values:
        t = parse_ts(v)
        if t and (best_t is None or t > best_t):
            best, best_t = v, t
    return best


class Dashboard:
    def __init__(self, repo: Path, pm_dir: Path, transcripts_dir: Path | None | bool = True) -> None:
        self.repo = repo
        self.pm_dir = pm_dir
        tdir = default_transcripts_dir(repo) if transcripts_dir is True else (transcripts_dir or None)
        self.transcripts = TranscriptReader(tdir, repo)

    @property
    def inbox_path(self) -> Path:
        return self.pm_dir / "inbox.jsonl"

    def load_state(self) -> tuple[dict, str, str | None]:
        return state.load(self.pm_dir / "state.json")

    def known_workers(self) -> dict[str, str]:
        st, _, _ = self.load_state()
        names = {w["id"]: w["name"] for w in st["workers"]}
        if not names:   # no state yet: fall back to ACTIVE_WORK.md
            aw = docs.parse_active_work(docs.read_text(self.repo / "ACTIVE_WORK.md"))
            names = {w["id"]: w["title"] for w in aw["workers"]}
        return names

    def build(self, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        errors: list[str] = []
        st, st_status, st_error = self.load_state()

        def guard(label, fn, default):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - one bad source must not blank the page
                errors.append(f"{label}: {exc.__class__.__name__}")
                return default

        git = guard("git", lambda: gitinfo.snapshot(self.repo), {"ok": False, "dirty": [], "commits": []})
        roadmap = guard("roadmap", lambda: docs.parse_roadmap(docs.read_text(self.repo / "ROADMAP.md")), {"ok": False, "milestones": []})
        apply_hebrew_titles(roadmap, st["roadmap_titles_hebrew"])
        active = guard("active_work", lambda: docs.parse_active_work(docs.read_text(self.repo / "ACTIVE_WORK.md")), {"ok": False, "workers": []})
        adrs = guard("decisions", lambda: docs.parse_adrs(docs.read_text(self.repo / "DECISIONS.md")), [])
        memory = guard("memory", lambda: docs.memory_current_state(docs.read_text(self.repo / "MEMORY.md")), {"ok": False})
        days = guard("daily", lambda: daily.load(self.pm_dir / "daily"), {"today_entry": None, "history": []})

        # Workers: state.json is primary; ACTIVE_WORK.md only fills in when state has none.
        workers = st["workers"]
        workers_source = "state"
        if not workers and active.get("workers"):
            workers_source = "active_work"
            workers = [state.normalize({"workers": [{
                "id": w["id"], "name": w["title"], "status": w["status"], "task": w["title"],
                "now_hebrew": w["status_text"],
            }]})["workers"][0] for w in active["workers"]]

        ownership = guard("owners", lambda: owners.group_dirty(git.get("dirty", []), workers, st["pm"]["owns"]),
                          {"groups": {}, "warnings": [], "unowned": [], "shared": []})

        views = []
        for w in workers:
            tr = guard(f"transcript {w['id']}", lambda w=w: self.transcripts.for_titles(w["transcript_titles"] or [w["name"]]), None)
            ctx = resolve_context(w["context"], tr.get("context_estimate") if tr else None)
            views.append({
                **w,
                "context_resolved": ctx,
                "transcript": tr,
                "last_activity_at": _latest(w["last_update"]["at"], tr["last_activity_at"] if tr else None),
                "git_files": ownership["groups"].get(w["id"], []),
            })
        pm_tr = guard("transcript PM", lambda: self.transcripts.for_titles(st["pm"]["transcript_titles"] or [st["pm"]["name"]]), None)

        handled = set(st["inbox_handled"])
        requests = guard("inbox", lambda: inbox.read_all(self.inbox_path, handled), [])
        names = {w["id"]: w["name"] for w in workers}
        for r in requests:
            r["copy_text"] = inbox.copy_text(r, names)
            r["label"] = inbox.REQUEST_TYPES.get(r.get("type"), (False, r.get("type"), ""))[1]

        return {
            "generated_at": now.isoformat(timespec="seconds"),
            "state_status": st_status,
            "state_error": st_error,
            "state": st,
            "workers": views,
            "workers_source": workers_source,
            "pm": {**st["pm"], "transcript": pm_tr},
            "git": git,
            "ownership": ownership,
            "roadmap": roadmap,
            "roadmap_focus": guard("roadmap_focus", lambda: roadmap_focus(roadmap, st["roadmap_notes"]), {"here": None, "next": None}),
            "active_work": active,
            "adrs": adrs,
            "memory": memory,
            "daily": days,
            "inbox": list(reversed(requests)),
            "request_types": {k: {"needs_worker": v[0], "label": v[1]} for k, v in inbox.REQUEST_TYPES.items()},
            "handoff_files": self._handoff_files(),
            "efficiency": efficiency(views, st),
            "errors": errors,
        }

    def _handoff_files(self) -> list[dict]:
        out = []
        for name in ("MEMORY.md", "ACTIVE_WORK.md"):
            try:
                mtime = (self.repo / name).stat().st_mtime
                out.append({"name": name, "modified_at": datetime.fromtimestamp(mtime, timezone.utc).isoformat(timespec="seconds")})
            except OSError:
                out.append({"name": name, "modified_at": None})
        return out


def _milestone_lookup(m: dict, mapping: dict):
    title = m.get("title_en") or m["title"]
    for key in (f"M{m['number']}", f"m{m['number']}", str(m["number"]), title):
        if mapping.get(key):
            return mapping[key]
    return None


def apply_hebrew_titles(roadmap: dict, titles: dict[str, str]) -> None:
    """Replace ROADMAP.md's English headings with the PM's Hebrew titles, when given.

    The English heading is kept as ``title_en``; without a Hebrew title nothing changes.
    """
    for m in roadmap.get("milestones", []):
        if m.get("number") is None:
            continue
        he = _milestone_lookup(m, titles)
        m["title_en"] = m["title"]
        if he:
            m["title"] = he


def milestone_notes(m: dict, notes: dict[str, list[str]]) -> list[str]:
    """Hebrew notes the PM wrote for a milestone (never the raw ROADMAP items)."""
    return _milestone_lookup(m, notes) or []


def roadmap_focus(roadmap: dict, notes: dict[str, list[str]]) -> dict:
    """Pick the milestone "we are here" and "the next step" for the owner.

    "Here" = the highest milestone at/before the current one (or before the next
    one, when nothing is in progress) that still has Hebrew notes, open follow-ups
    or unfinished work. A formally closed milestone (✅) with open follow-ups is
    therefore still "here". "Next" = the first not-started milestone after it.
    """
    ms = [m for m in roadmap.get("milestones", []) if m.get("number") is not None]
    current, nxt = roadmap.get("current"), roadmap.get("next")
    limit = current if current is not None else (nxt - 1 if nxt is not None else None)

    def view(m: dict | None) -> dict | None:
        if not m:
            return None
        return {"number": m["number"], "title": m["title"], "status": m["status"], "notes": milestone_notes(m, notes)}

    here = None
    if limit is not None:
        for m in sorted(ms, key=lambda m: m["number"], reverse=True):
            if m["number"] > limit:
                continue
            if milestone_notes(m, notes) or m["open_follow_ups"] or m["status"] in {"in_progress", "ready_to_close"}:
                here = m
                break
    after = here["number"] if here else -1
    next_m = next((m for m in sorted(ms, key=lambda m: m["number"])
                   if m["number"] > after and m["status"] in {"next", "not_started"}), None)
    return {"here": view(here), "next": view(next_m)}


def efficiency(views: list[dict], st: dict) -> dict:
    by_status: dict[str, int] = {}
    for w in views:
        by_status[w["status"]] = by_status.get(w["status"], 0) + 1
    risky = [
        {"id": w["id"], "name": w["name"], **w["context_resolved"]}
        for w in views
        if w["context_resolved"]["percent"] is not None and w["context_resolved"]["percent"] >= 70
        and w["status"] not in {"DONE"}
    ]
    activity = [
        {"id": w["id"], "name": w["name"], "turns_last_hour": w["transcript"]["turns_last_hour"]}
        for w in views if w.get("transcript")
    ]

    recs: list[dict] = []
    for r in risky:
        if r["level"] in {"near", "handoff"}:
            recs.append({"level": "bad", "text": f"{r['name']} צבר context גבוה ({r['percent']:.0f}%) — כדאי לסיים בנקודה בטוחה ולעשות handoff לעובד חדש."})
        else:
            recs.append({"level": "warn", "text": f"ה-context של {r['name']} מתקרב לגבול ({r['percent']:.0f}%) — לא כדאי לתת לו משימה גדולה חדשה."})
    usage = st.get("plan_usage")
    if usage:
        five = usage.get("five_hour_percent")
        week = usage.get("weekly_percent")
        if five is not None and five >= 95:
            recs.append({"level": "bad", "text": "המכסה הקצרה (5 שעות) כמעט נגמרה — כדאי לעצור בנקודות בטוחות עד האיפוס."})
        elif five is not None and five >= 80:
            recs.append({"level": "warn", "text": "המכסה הקצרה (5 שעות) קרובה לסיום — לא כדאי להתחיל משימה גדולה."})
        if week is not None and week >= 80:
            recs.append({"level": "warn", "text": "המכסה השבועית גבוהה — כדאי לתעדף רק את החשוב."})
    waiting = [w for w in views if w["status"] in {"WAITING", "BLOCKED"}]
    if waiting and all(w["depends_on"] for w in waiting):
        recs.append({"level": "info", "text": "העובדים שממתינים מחכים לעבודה של עובד אחר — אין יתרון בהפעלת עובד נוסף כרגע."})
    for a in activity:
        if a["turns_last_hour"] >= 120:
            recs.append({"level": "info", "text": f"פעילות גבוהה במיוחד אצל {a['name']} בשעה האחרונה (הערכה) — כדאי לוודא שהוא לא תקוע בלולאה."})
    eff_pm = st.get("efficiency") or {}
    for text in eff_pm.get("recommendations_hebrew", []):
        recs.append({"level": "pm", "text": text})

    return {
        "active": by_status.get("ACTIVE", 0),
        "waiting": by_status.get("WAITING", 0),
        "blocked": by_status.get("BLOCKED", 0),
        "done": by_status.get("DONE", 0),
        "context_risk": risky,
        "plan_usage": usage,
        "activity": activity,
        "recommendations": recs,
        "pm_recommendations_at": eff_pm.get("at"),
    }
