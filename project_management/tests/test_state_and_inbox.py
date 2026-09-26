import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from project_management.dashboard import Dashboard, context_level, efficiency, resolve_context
from project_management.sources import inbox, state

EXAMPLE = Path(__file__).resolve().parents[1] / "state.example.json"


def test_example_state_is_valid():
    st, status, err = state.load(EXAMPLE)
    assert status == "ok" and err is None
    assert st["workers"][0]["id"] == "W1"
    assert st["pm"]["deep_link"].startswith("claude://")


def test_missing_file(tmp_path):
    st, status, _ = state.load(tmp_path / "state.json")
    assert status == "missing" and st["workers"] == [] and st["project_summary"]["active"] == ""


@pytest.mark.parametrize("content", [b'{"workers": [{"id": "W1"', b"", b"\xff\xfe\x00", b"[1,2,3]", b"null"])
def test_corrupt_or_half_written(tmp_path, content):
    p = tmp_path / "state.json"
    p.write_bytes(content)
    st, status, err = state.load(p)
    assert status == "corrupt" and err and st["workers"] == []


def test_missing_and_wrong_typed_fields_degrade():
    st = state.normalize({
        "workers": [
            {},
            {"id": "W9", "status": "dancing", "done": "one item", "owns": None, "tests": "nope",
             "context": {"percent": 250}, "deep_link": "javascript:alert(1)", "committed": "abc1234",
             "manual_test": {"status": "WHATEVER"}},
            "not a dict",
        ],
        "tasks": [{"status": "weird"}],
        "attention": [{"type": "unknown"}],
        "timeline": [{"event": "exploded"}],
        "plan_usage": "x",
        "inbox_handled": [1, "2", "x"],
    })
    assert len(st["workers"]) == 2
    w0, w9 = st["workers"]
    assert w0["name"] and w0["status"] == "UNKNOWN" and w0["done"] == []
    assert w9["status"] == "UNKNOWN" and w9["done"] == ["one item"] and w9["owns"] == []
    assert w9["context"]["percent"] is None  # out of range → dropped, never invented
    assert w9["deep_link"] is None           # only claude:// links
    assert w9["committed"] is True and w9["commit"] == "abc1234"
    assert w9["manual_test"]["status"] == "not_needed"
    assert st["tasks"][0]["status"] == "PENDING_PM"
    assert st["timeline"][0]["event"] == "other"
    assert st["plan_usage"] is None and st["efficiency"] is None
    assert st["inbox_handled"] == [1, 2]


def test_context_levels_and_resolution():
    assert context_level(None) is None
    assert [context_level(p) for p in (10, 70, 84.9, 85, 95)] == ["healthy", "high", "high", "near", "handoff"]
    pm = {"percent": 30, "source": "exact", "at": "2026-09-26T15:00:00+03:00"}
    newer_est = {"percent": 50, "at": "2026-09-26T12:30:00Z"}   # 15:30 local → newer
    older_est = {"percent": 50, "at": "2026-09-26T11:00:00Z"}
    assert resolve_context(pm, newer_est)["source"] == "estimate"
    assert resolve_context(pm, older_est)["source"] == "exact"
    assert resolve_context({"percent": None}, None)["percent"] is None


def test_efficiency_rules_never_invent_usage():
    view = lambda wid, status, pct, deps=(): {  # noqa: E731
        "id": wid, "name": wid, "status": status, "depends_on": list(deps), "transcript": None,
        "context_resolved": {"percent": pct, "level": context_level(pct), "source": "exact", "at": None},
    }
    views = [view("W1", "ACTIVE", 90), view("W2", "WAITING", 10, ["W1"])]
    eff = efficiency(views, state.normalize({}))
    assert eff["plan_usage"] is None
    texts = " ".join(r["text"] for r in eff["recommendations"])
    assert "handoff" in texts and "אין יתרון" in texts
    eff2 = efficiency(views, state.normalize({"plan_usage": {"five_hour_percent": 88},
                                               "efficiency": {"recommendations_hebrew": ["המלצת מנהל"]}}))
    texts2 = [r["text"] for r in eff2["recommendations"]]
    assert any("המכסה הקצרה" in t for t in texts2) and "המלצת מנהל" in texts2


def test_inbox_append_and_copy_text(tmp_path):
    p = tmp_path / "inbox.jsonl"
    a = inbox.append(p, "continue_worker", "W2", "", {"W1", "W2"})
    b = inbox.append(p, "new_task", "", "רעיון חדש", {"W1", "W2"})
    assert (a["id"], b["id"]) == (1, 2)
    items = inbox.read_all(p, handled={1})
    assert [i["status"] for i in items] == ["handled", "pending"]
    txt = inbox.copy_text(a, {"W2": "עובד החרגות"})
    assert txt == "[בקשה מהדשבורד #1] המשך את עובד החרגות."
    assert "רעיון חדש" in inbox.copy_text(b, {})


@pytest.mark.parametrize("rtype,worker,text", [
    ("rm_rf", "", ""), ("pause_worker", "", ""), ("pause_worker", "W7", ""),
    ("message_worker", "W1", ""), ("new_task", "", "x" * 5000),
])
def test_inbox_rejects_bad_requests(tmp_path, rtype, worker, text):
    with pytest.raises(inbox.InboxError):
        inbox.append(tmp_path / "i.jsonl", rtype, worker, text, {"W1"})


def test_inbox_skips_corrupt_lines(tmp_path):
    p = tmp_path / "inbox.jsonl"
    p.write_text('{"id": 1, "type": "summarize"}\nnot json\n{"id": "x"}\n', encoding="utf-8")
    assert [i["id"] for i in inbox.read_all(p)] == [1]
    assert inbox.append(p, "summarize", "", "", set())["id"] == 2


def test_dashboard_builds_without_state(tmp_path):
    (tmp_path / "ROADMAP.md").write_text("## Milestone 1 — A\n- [ ] x\n", encoding="utf-8")
    (tmp_path / "ACTIVE_WORK.md").write_text("## Workers\n### W1: Thing. Status: ACTIVE\n- a\n", encoding="utf-8")
    pm_dir = tmp_path / "pm"
    pm_dir.mkdir()
    d = Dashboard(tmp_path, pm_dir, transcripts_dir=None).build(now=datetime(2026, 9, 26, tzinfo=timezone.utc))
    assert d["state_status"] == "missing"
    assert d["workers_source"] == "active_work" and d["workers"][0]["id"] == "W1"
    assert d["git"]["ok"] is False or "dirty" in d["git"]   # tmp dir is not a repo: reported, no crash
    json.dumps(d)  # fully serializable


def test_overview_and_roadmap_notes_additive():
    st = state.normalize({
        "overview_hebrew": "שורה 1\nשורה 2",
        "roadmap_notes": {"M2": ["חסר א", "", 5], "": ["x"], "Search": "single"},
    })
    assert st["overview_hebrew"] == "שורה 1\nשורה 2"
    assert st["roadmap_notes"] == {"M2": ["חסר א", "5"], "Search": ["single"]}
    old = state.normalize({"schema_version": 1})
    assert old["overview_hebrew"] == "" and old["roadmap_notes"] == {}
    assert state.normalize({"roadmap_notes": ["not", "a", "dict"]})["roadmap_notes"] == {}
    assert state.load(EXAMPLE)[0]["roadmap_notes"]["M2"]


ROADMAP_M1_OPEN = """## Milestone 0 — A ✅
- [x] a
## Milestone 1 — B ✅
- [x] b
### Open follow-ups
- [ ] english item
## Milestone 2 — C
- [ ] c
## Milestone 3 — D
- [ ] d
"""


def test_roadmap_focus_we_are_here():
    from project_management.dashboard import roadmap_focus
    from project_management.sources import docs

    rm = docs.parse_roadmap(ROADMAP_M1_OPEN)
    f = roadmap_focus(rm, {"M1": ["לסיים את מסך הסינון"], "M2": ["אישור שלך"]})
    assert f["here"]["number"] == 1 and f["here"]["notes"] == ["לסיים את מסך הסינון"]
    assert f["next"]["number"] == 2 and f["next"]["notes"] == ["אישור שלך"]
    # No Hebrew notes → no notes (raw English follow-ups never leak); still "here" via open follow-ups.
    f2 = roadmap_focus(rm, {})
    assert f2["here"]["number"] == 1 and f2["here"]["notes"] == []
    assert "english item" not in json.dumps(f2)
    # A milestone in progress is "here"; the next is the first not-started one after it.
    rm3 = docs.parse_roadmap("## Milestone 1 — B ✅\n- [x] b\n## Milestone 2 — C\n- [x] c\n- [ ] d\n## Milestone 3 — D\n- [ ] e\n")
    f3 = roadmap_focus(rm3, {})
    assert (f3["here"]["number"], f3["next"]["number"]) == (2, 3)
    # Everything closed and nothing open → nothing highlighted, only "next".
    rm4 = docs.parse_roadmap("## Milestone 1 — B ✅\n- [x] b\n## Milestone 2 — C\n- [ ] c\n")
    f4 = roadmap_focus(rm4, {})
    assert f4["here"] is None and f4["next"]["number"] == 2


def test_roadmap_titles_hebrew_with_fallback():
    from project_management.dashboard import apply_hebrew_titles, roadmap_focus
    from project_management.sources import docs

    titles = state.normalize({"roadmap_titles_hebrew": {"M1": "סריקת תמונות", "M2": "", "bad": 5}})["roadmap_titles_hebrew"]
    assert titles == {"M1": "סריקת תמונות", "bad": "5"}
    rm = docs.parse_roadmap(ROADMAP_M1_OPEN)
    apply_hebrew_titles(rm, titles)
    by_num = {m["number"]: m for m in rm["milestones"]}
    assert by_num[1]["title"] == "סריקת תמונות" and by_num[1]["title_en"] == "B"
    assert by_num[2]["title"] == "C"                      # no Hebrew title → English heading
    # Notes keyed by the English title still match after the Hebrew rename.
    f = roadmap_focus(rm, {"B": ["הערה"]})
    assert f["here"]["title"] == "סריקת תמונות" and f["here"]["notes"] == ["הערה"]
