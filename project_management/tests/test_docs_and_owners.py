from project_management.sources import docs, gitinfo, owners

ROADMAP = """# Roadmap

## Milestone 0 — Foundation ✅ (2026-09-26)
- [x] a
- [x] b

## Milestone 1 — Ingestion ✅ (2026-09-26)
- [x] c
### Open follow-ups
- [x] done follow-up
- [ ] open follow-up

## Milestone 2 — Search (NEXT — not started)
- [ ] x
- [ ] y

## Milestone 3 — People
- [ ] z

## Later / optional
- [ ] something
"""

ACTIVE = """# Active Work
Last updated: 2026-09-26 ~14:55 (PM).

## Workers

### W1: Quality viewer. Status: ACTIVE (UX rework)
- Session: "עובד איכות". Mode: auto.
- Scope: stuff
  continued line

### W2: Exclusions. Status: WAITING (on W1's commit)
- Owns: scanner.py

### Not a worker heading
- ignored

## Reservations
- Schema: v3 = W2. **Next free: v5.**
"""


def test_roadmap_statuses_and_follow_ups():
    r = docs.parse_roadmap(ROADMAP)
    ms = {m["number"]: m for m in r["milestones"] if m["number"] is not None}
    assert ms[0]["status"] == "done" and ms[0]["done_count"] == 2 and ms[0]["total"] == 2
    assert ms[1]["status"] == "done" and ms[1]["total"] == 1
    assert [i["text"] for i in ms[1]["open_follow_ups"]] == ["open follow-up"]
    assert ms[2]["status"] == "next" and ms[2]["title"] == "Search"
    assert ms[3]["status"] == "not_started"
    assert r["next"] == 2 and r["current"] is None
    assert any(m["status"] == "other" for m in r["milestones"])


def test_roadmap_in_progress_and_ready_to_close():
    text = "## Milestone 2 — A\n- [x] a\n- [ ] b\n## Milestone 3 — B\n- [x] c\n"
    ms = {m["number"]: m for m in docs.parse_roadmap(text)["milestones"]}
    assert ms[2]["status"] == "in_progress"
    assert ms[3]["status"] == "ready_to_close"


def test_roadmap_missing_or_garbage():
    assert docs.parse_roadmap(None)["ok"] is False
    assert docs.parse_roadmap("no headings at all\n- [ ] x")["milestones"] == []


def test_active_work_parse():
    a = docs.parse_active_work(ACTIVE)
    assert a["updated"].startswith("2026-09-26")
    assert [(w["id"], w["status"]) for w in a["workers"]] == [("W1", "ACTIVE"), ("W2", "WAITING")]
    assert "continued line" in a["workers"][0]["bullets"][1]
    assert a["reservations"] and "v5" in a["reservations"][0]
    assert "Workers" in [s["title"] for s in a["sections"]]


def test_active_work_unparseable_falls_back_to_raw():
    a = docs.parse_active_work("just some text without structure")
    assert a["ok"] and a["workers"] == [] and "just some text" in a["raw"]
    assert docs.parse_active_work(None)["ok"] is False


def test_adrs_sorted():
    text = "## ADR-012 — B\n## ADR-002 — A\n## Not an ADR\n"
    assert [a["id"] for a in docs.parse_adrs(text)] == ["ADR-002", "ADR-012"]


def test_status_z_parsing():
    out = " M app/a.py\0?? app/printing/x.py\0R  new.py\0old.py\0 D gone.py\0"
    files = gitinfo.parse_status_z(out)
    assert [(f["path"], f["kind"]) for f in files] == [
        ("app/a.py", "modified"), ("app/printing/x.py", "new"), ("new.py", "renamed"), ("gone.py", "deleted"),
    ]


def test_git_allowlist_rejects_unknown(tmp_path):
    import pytest
    with pytest.raises(gitinfo.GitError):
        gitinfo.run("push", tmp_path)


def test_glob_matching():
    assert owners.matches("app/printing/a/b.py", "app/printing/**")
    assert owners.matches("app/printing/b.py", "app/printing/")
    assert owners.matches("app/x.py", "app/*.py")
    assert not owners.matches("app/sub/x.py", "app/*.py")
    assert owners.matches("MEMORY.md", "memory.md")  # Windows: case-insensitive
    assert not owners.matches("app/x.py", "")


def _f(path):
    return {"path": path, "code": " M", "kind": "modified"}


def test_group_dirty_single_owner_no_warnings():
    workers = [{"id": "W1", "owns": ["app/**"]}]
    res = owners.group_dirty([_f("app/a.py")], workers, [])
    assert list(res["groups"]) == ["W1"] and res["warnings"] == []


def test_group_dirty_mixed_shared_unowned():
    workers = [
        {"id": "W1", "owns": ["app/printing/**", "app/db/database.py", "MEMORY.md"]},
        {"id": "W2", "owns": ["app/ingest/scanner.py", "app/db/database.py"]},
    ]
    dirty = [_f("app/printing/p.py"), _f("app/ingest/scanner.py"), _f("app/db/database.py"),
             _f("MEMORY.md"), _f("random.txt")]
    res = owners.group_dirty(dirty, workers, ["MEMORY.md", "ACTIVE_WORK.md"])
    types = {w["type"] for w in res["warnings"]}
    assert types == {"mixed", "shared", "unowned"}
    assert [f["path"] for f in res["shared"]] == ["app/db/database.py"]
    assert [f["path"] for f in res["unowned"]] == ["random.txt"]
    # MEMORY.md belongs to W1 and PM, but PM co-ownership is not a "shared" conflict
    assert "MEMORY.md" not in [f["path"] for f in res["shared"]]
    assert {f["path"] for f in res["groups"]["PM"]} == {"MEMORY.md"}


def test_group_dirty_pm_docs_only_is_not_mixed():
    res = owners.group_dirty([_f("ACTIVE_WORK.md")], [{"id": "W1", "owns": ["app/**"]}], ["ACTIVE_WORK.md"])
    assert res["warnings"] == []
