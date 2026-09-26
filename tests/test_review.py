"""Human review labels (ADR-018) and the v4 migration (ADR-017)."""

import json
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db.database import SCHEMA, SCHEMA_VERSION, Database
from app.main import create_app
from app.vision.quality.classical import combined_quality_score

# Metrics produced by the automatic analysis; a human label must never change them.
AUTO_COLUMNS = ("sharpness", "brightness", "contrast", "dark_fraction", "bright_fraction", "exposure_issue",
                "quality_score", "is_blurry", "is_screenshot", "screenshot_reason", "duplicate_group_id",
                "is_group_best", "width", "height")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def scanned(client, library):
    root, _ = library
    body = client.post("/api/libraries", json={"path": str(root)}).json()
    assert client.app.state.jobs.wait(body["job"]["id"], timeout=120)["status"] == "done"
    lib_id = body["library"]["id"]
    items = client.get(f"/api/photos?library_id={lib_id}&limit=500").json()["items"]
    return lib_id, {os.path.basename(p["source_path"]): p for p in items}


def _ids(client, lib_id, filter_name):
    items = client.get(f"/api/photos?library_id={lib_id}&filter={filter_name}&limit=500").json()["items"]
    return {os.path.basename(p["source_path"]) for p in items}


def _auto(client, pid):
    p = client.get(f"/api/photos/{pid}").json()
    return {k: p[k] for k in AUTO_COLUMNS}


def test_photo_detail_has_measurements_print_and_rules(client, scanned):
    _, photos = scanned
    p = client.get(f"/api/photos/{photos['a.jpg']['id']}").json()
    assert p["print"]["width"] == 1400 and p["print"]["extremely_low"] is False
    assert {s["label"] for s in p["print"]["sizes"]} >= {"6×9 cm", "30×30 cm"}
    assert p["analysis"]["sharpness"]["blur_threshold"] == 40
    assert set(p["analysis"]["quality"]["components"]) == {"sharpness", "exposure", "contrast"}
    assert p["extension_matches_format"] is True
    assert p["review"] is None
    assert p["original_url"].startswith(f"/api/photos/{p['id']}/original?v=")

    tiny = client.get(f"/api/photos/{photos['tiny.jpg']['id']}").json()  # 320x240
    assert tiny["print"]["extremely_low"] is True
    assert "Extremely low resolution" in tiny["signals"]
    assert "Extremely low resolution" not in p["signals"]


def test_original_endpoint_serves_the_untouched_file(client, scanned, library):
    _, paths = library
    _, photos = scanned
    r = client.get(f"/api/photos/{photos['a.jpg']['id']}/original")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.content == paths["a"].read_bytes()


def test_extension_mismatch_is_reported(client, library):
    root, paths = library
    os.replace(paths["b"], root / "really_png.jpg")  # PNG bytes with a .jpg name
    body = client.post("/api/libraries", json={"path": str(root)}).json()
    client.app.state.jobs.wait(body["job"]["id"], timeout=120)
    items = client.get(f"/api/photos?library_id={body['library']['id']}&limit=500").json()["items"]
    pid = next(p["id"] for p in items if p["rel_path"] == "really_png.jpg")
    detail = client.get(f"/api/photos/{pid}").json()
    assert detail["format"] == "PNG" and detail["extension_matches_format"] is False


def test_review_is_stored_separately_and_never_changes_analysis(client, scanned):
    lib_id, photos = scanned
    pid = photos["blurry.jpg"]["id"]
    before = _auto(client, pid)

    r = client.put(f"/api/photos/{pid}/review", json={"verdict": "good", "reasons": [], "note": "  fine for me "})
    assert r.status_code == 200, r.text
    label = r.json()
    assert label["verdict"] == "good" and label["note"] == "fine for me"
    assert label["auto_snapshot"]["is_blurry"] is True  # what the automatic analysis said at label time

    assert _auto(client, pid) == before
    assert client.get(f"/api/photos/{pid}").json()["review"]["verdict"] == "good"

    # Change of mind overwrites the label only.
    client.put(f"/api/photos/{pid}/review", json={"verdict": "bad", "reasons": ["blurry"]})
    assert client.get(f"/api/photos/{pid}").json()["review"]["reasons"] == ["blurry"]
    assert _auto(client, pid) == before

    assert client.delete(f"/api/photos/{pid}/review").json() == {"deleted": True}
    assert client.get(f"/api/photos/{pid}").json()["review"] is None
    assert _auto(client, pid) == before


def test_review_validation(client, scanned):
    _, photos = scanned
    pid = photos["a.jpg"]["id"]
    assert client.put(f"/api/photos/{pid}/review", json={"verdict": "maybe"}).status_code == 400
    assert client.put(f"/api/photos/{pid}/review", json={"verdict": "bad", "reasons": ["ugly"]}).status_code == 400
    assert client.put("/api/photos/999999/review", json={"verdict": "good"}).status_code == 404


def test_review_filters_and_disagreement(client, scanned):
    lib_id, photos = scanned
    put = lambda name, verdict, reasons=(): client.put(  # noqa: E731
        f"/api/photos/{photos[name]['id']}/review", json={"verdict": verdict, "reasons": list(reasons)})
    put("blurry.jpg", "bad", ["blurry"])   # flagged + bad  -> agree
    put("dark.jpg", "good")                # flagged + good -> disagree (false alarm)
    put("b.png", "bad", ["other"])         # unflagged + bad -> disagree (miss)
    put("rotated.jpg", "good")             # unflagged + good -> agree

    assert _ids(client, lib_id, "review_good") == {"dark.jpg", "rotated.jpg"}
    assert _ids(client, lib_id, "review_bad") == {"blurry.jpg", "b.png"}
    assert _ids(client, lib_id, "review_disagree") == {"dark.jpg", "b.png"}
    unreviewed = _ids(client, lib_id, "unreviewed")
    assert "a.jpg" in unreviewed and "blurry.jpg" not in unreviewed

    items = client.get(f"/api/photos?library_id={lib_id}&filter=review_bad").json()["items"]
    assert {p["review_verdict"] for p in items} == {"bad"}

    s = client.get(f"/api/libraries/{lib_id}/review/stats").json()
    assert (s["reviewed"], s["good"], s["bad"], s["agree"], s["disagree"]) == (4, 2, 2, 2, 2)
    assert s["flags"]["blurry"] == {"flagged_reviewed": 1, "flagged_bad": 1, "flagged_good": 0,
                                    "flag_precision": 1.0, "missed": 0}
    assert s["flags"]["exposure"]["flagged_good"] == 1 and s["flags"]["exposure"]["flag_precision"] == 0.0
    assert client.get(f"/api/libraries/{lib_id}/stats").json()["stats"]["reviewed"] == 4


def test_extreme_low_res_filter_and_stats(client, scanned):
    lib_id, _ = scanned
    assert _ids(client, lib_id, "extreme_low_res") == {"tiny.jpg"}
    assert client.get(f"/api/libraries/{lib_id}/stats").json()["stats"]["extreme_low_res"] == 1


def test_label_survives_rescan_and_follows_identical_copies(client, scanned):
    lib_id, photos = scanned
    client.put(f"/api/photos/{photos['a.jpg']['id']}/review", json={"verdict": "good"})
    job = client.post(f"/api/libraries/{lib_id}/scan").json()
    client.app.state.jobs.wait(job["id"], timeout=120)
    assert client.get(f"/api/photos/{photos['a.jpg']['id']}").json()["review"]["verdict"] == "good"
    # a_copy.jpg has the same bytes -> same label (the label belongs to the photo content).
    assert client.get(f"/api/photos/{photos['a_copy.jpg']['id']}").json()["review"]["verdict"] == "good"
    # ...but it is counted once in the evaluation.
    assert client.get(f"/api/libraries/{lib_id}/review/stats").json()["reviewed"] == 1


def test_export_json_and_csv(client, scanned):
    lib_id, photos = scanned
    client.put(f"/api/photos/{photos['blurry.jpg']['id']}/review", json={"verdict": "bad", "reasons": ["blurry"], "note": "רך"})
    rows = client.get(f"/api/libraries/{lib_id}/review/export").json()
    assert len(rows) == 1 and rows[0]["verdict"] == "bad" and rows[0]["reasons"] == ["blurry"]
    assert rows[0]["is_blurry"] == 1 and rows[0]["auto_snapshot"]["is_blurry"] is True
    r = client.get(f"/api/libraries/{lib_id}/review/export?format=csv")
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    text = r.content.decode("utf-8-sig")
    assert "blurry.jpg" in text and "רך" in text
    assert client.get(f"/api/libraries/{lib_id}/review/export?format=xml").status_code == 400


def test_deleting_library_deletes_its_labels(client, scanned):
    lib_id, photos = scanned
    client.put(f"/api/photos/{photos['a.jpg']['id']}/review", json={"verdict": "good"})
    assert client.delete(f"/api/libraries/{lib_id}").status_code == 200
    with client.app.state.db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM review_labels").fetchone()[0] == 0


def _v3_schema() -> str:
    """The schema as it was before v4: photos still had the 1-megapixel is_low_res flag, no review_labels."""
    old = SCHEMA.replace(
        "    is_blurry           INTEGER NOT NULL DEFAULT 0,\n",
        "    is_blurry           INTEGER NOT NULL DEFAULT 0,\n    is_low_res          INTEGER NOT NULL DEFAULT 0,\n",
    )
    assert old != SCHEMA
    start = old.index("-- Human review labels")
    return old[:start] + old[old.index("CREATE TABLE IF NOT EXISTS jobs"):]


def test_migration_to_v4_drops_low_res_flag_and_recomputes_quality(tmp_path):
    path = tmp_path / "v3.sqlite3"
    with sqlite3.connect(path) as c:
        c.executescript(_v3_schema())
        c.execute("INSERT INTO meta VALUES('schema_version', '3')")
        c.execute("INSERT INTO libraries(id, root_path, name, created_at) VALUES(1, 'C:/A', 'A', 'x')")
        c.execute(
            "INSERT INTO photos(id, library_id, source_path, rel_path, status, width, height, sharpness, contrast, "
            "exposure_issue, quality_score, is_low_res) VALUES(1, 1, 'C:/A/x.jpg', 'x.jpg', 'ok', 1024, 768, 300, 40, "
            "NULL, 0.1, 1)"
        )
    db = Database(path)
    assert db.initialize() == [4]
    with db.connect() as c:
        assert c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == str(SCHEMA_VERSION)
        cols = [r[1] for r in c.execute("PRAGMA table_info(photos)")]
        assert "is_low_res" not in cols
        row = c.execute("SELECT width, height, quality_score FROM photos WHERE id = 1").fetchone()
        assert (row["width"], row["height"]) == (1024, 768)  # native dimensions kept
        assert row["quality_score"] == combined_quality_score(300, None, 40)
        assert c.execute("SELECT COUNT(*) FROM review_labels").fetchone()[0] == 0
    assert db.initialize() == []  # idempotent


def test_app_start_after_migration_refreshes_duplicate_best(tmp_path, settings):
    """Two near-identical copies: the old rule picked the sharper-by-noise small copy; v4 prefers the original."""
    with sqlite3.connect(settings.db_path) as c:
        c.executescript(_v3_schema())
        c.execute("INSERT INTO meta VALUES('schema_version', '3')")
        c.execute("INSERT INTO libraries(id, root_path, name, created_at) VALUES(1, 'C:/A', 'A', 'x')")
        c.execute("INSERT INTO duplicate_groups(id, library_id, kind, best_photo_id, size) VALUES(1, 1, 'near', 2, 2)")
        for pid, w, h, sharp in ((1, 4032, 3024, 400), (2, 1600, 1200, 460)):
            c.execute(
                "INSERT INTO photos(id, library_id, source_path, rel_path, status, content_hash, phash, dhash, width, "
                "height, sharpness, contrast, quality_score, duplicate_group_id, is_group_best) "
                "VALUES(?, 1, ?, ?, 'ok', ?, 'ffffffffffffffff', '0000000000000000', ?, ?, ?, 45, 0.9, 1, ?)",
                (pid, f"C:/A/{pid}.jpg", f"{pid}.jpg", f"h{pid}", w, h, sharp, int(pid == 2)),
            )
    with TestClient(create_app(settings)) as client:
        rows = {p["id"]: p for p in client.get("/api/photos?library_id=1").json()["items"]}
    assert rows[1]["is_group_best"] == 1 and rows[2]["is_group_best"] == 0
    assert json.dumps(rows)  # serializable


# ---------------------------------------------------------------- filter review (ADR-018)
def _summary(client, lib_id):
    return client.get(f"/api/libraries/{lib_id}/filter/summary").json()


def _assert_consistent(client, lib_id):
    """One photo = one place: kept/filtered partition everything; tabs partition `filtered`."""
    s = _summary(client, lib_id)
    kept, filtered = _ids(client, lib_id, "kept"), _ids(client, lib_id, "filtered")
    assert not kept & filtered and len(kept) + len(filtered) == s["total"]
    assert s["kept"] + s["filtered"] == s["total"] and sum(s["by_reason"].values()) == s["filtered"]
    tabs = [_ids(client, lib_id, f"reason_{r}") for r in s["by_reason"]]
    assert set().union(*tabs) == filtered and sum(map(len, tabs)) == len(filtered)
    # Never two copies of one duplicate group in "kept".
    items = client.get(f"/api/photos?library_id={lib_id}&filter=kept&limit=500").json()["items"]
    groups = [p["duplicate_group_id"] for p in items if p["duplicate_group_id"]]
    assert len(groups) == len(set(groups))
    return s


def test_filter_summary_and_effective_decision(client, scanned):
    lib_id, photos = scanned
    s = _assert_consistent(client, lib_id)
    assert s["by_reason"]["duplicate"] == 2  # a_copy + a_small are alternates of a.jpg
    assert s["by_reason"]["low_quality"] == 2  # blurry.jpg + tiny.jpg (blur and too small merged)
    assert s["feedback"] == {"restored": 0, "should_filter": 0, "duplicate_picks_changed": 0}

    # Restoring a photo filtered for a technical reason keeps it; removing a kept one filters it.
    client.put(f"/api/photos/{photos['blurry.jpg']['id']}/review", json={"verdict": "good"})
    client.put(f"/api/photos/{photos['rotated.jpg']['id']}/review", json={"verdict": "bad"})
    assert "blurry.jpg" in _ids(client, lib_id, "kept") and "rotated.jpg" in _ids(client, lib_id, "reason_manual")
    s2 = _assert_consistent(client, lib_id)
    assert s2["feedback"]["restored"] == 1 and s2["feedback"]["should_filter"] == 1
    assert _ids(client, lib_id, "changes") == {"blurry.jpg", "rotated.jpg"}
    assert _ids(client, lib_id, "blurry") >= {"blurry.jpg"}  # automatic flag itself is unchanged


def test_restoring_a_duplicate_copy_never_keeps_two_copies(client, scanned):
    lib_id, photos = scanned
    alt = photos["a_small.jpg"]  # near-duplicate alternate of a.jpg
    before = (_summary(client, lib_id), _ids(client, lib_id, "kept"), _ids(client, lib_id, "filtered"))

    client.put(f"/api/photos/{alt['id']}/review", json={"verdict": "good"})  # e.g. restored in another tab
    s = _assert_consistent(client, lib_id)
    kept = _ids(client, lib_id, "kept")
    assert "a_small.jpg" not in kept and len(kept & {"a.jpg", "a_copy.jpg", "a_small.jpg"}) == 1
    assert "a_small.jpg" in _ids(client, lib_id, "reason_duplicate")  # still shown once, as a duplicate
    assert s["feedback"]["restored"] == 0

    # Undo returns exactly the previous state.
    client.delete(f"/api/photos/{alt['id']}/review")
    assert (_summary(client, lib_id), _ids(client, lib_id, "kept"), _ids(client, lib_id, "filtered")) == before

    # The way to keep that copy instead: pick it — still exactly one copy kept.
    client.put(f"/api/photos/{alt['id']}/keep")
    kept = _ids(client, lib_id, "kept")
    assert "a_small.jpg" in kept and len(kept & {"a.jpg", "a_copy.jpg", "a_small.jpg"}) == 1
    _assert_consistent(client, lib_id)


def test_user_can_change_duplicate_keeper_and_it_survives_rescan(client, scanned):
    lib_id, photos = scanned
    small = photos["a_small.jpg"]["id"]
    before = client.get(f"/api/photos/{small}").json()
    assert before["is_group_best"] == 0
    auto_best = before["duplicate_group"]["auto_best_photo_id"]

    r = client.put(f"/api/photos/{small}/keep")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["best_photo_id"] == small and body["auto_best_photo_id"] == auto_best
    assert [m["id"] for m in body["members"] if m["is_group_best"]] == [small]
    assert client.get(f"/api/libraries/{lib_id}/filter/summary").json()["feedback"]["duplicate_picks_changed"] == 1

    job = client.post(f"/api/libraries/{lib_id}/scan").json()
    client.app.state.jobs.wait(job["id"], timeout=120)
    assert client.get(f"/api/photos/{small}").json()["is_group_best"] == 1  # pick kept after regrouping

    back = client.delete(f"/api/photos/{small}/keep").json()
    assert back["best_photo_id"] == auto_best
    assert client.put(f"/api/photos/{photos['b.png']['id']}/keep").status_code == 400  # not in a group
    # Nothing was deleted along the way.
    assert len(client.get(f"/api/photos?library_id={lib_id}&limit=500").json()["items"]) == len(photos)


def test_v4_database_gets_the_additive_column(tmp_path):
    path = tmp_path / "early_v4.sqlite3"
    with sqlite3.connect(path) as c:
        c.executescript(SCHEMA.replace("    auto_best_photo_id INTEGER,                 -- what the automatic rule chose\n", ""))
        c.execute("INSERT INTO meta VALUES('schema_version', '4')")
        assert "auto_best_photo_id" not in [r[1] for r in c.execute("PRAGMA table_info(duplicate_groups)")]
    assert Database(path).initialize() == []
    with sqlite3.connect(path) as c:
        assert "auto_best_photo_id" in [r[1] for r in c.execute("PRAGMA table_info(duplicate_groups)")]


def test_deleting_library_leaves_no_filter_data_or_thumbnails(client, scanned, settings):
    lib_id, photos = scanned
    client.put(f"/api/photos/{photos['a_small.jpg']['id']}/keep")
    client.put(f"/api/photos/{photos['blurry.jpg']['id']}/review", json={"verdict": "good"})
    stray = settings.thumbnails_dir / "zz" / ("0" * 64 + ".jpg")  # orphan left by an older version
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"x")

    assert client.delete(f"/api/libraries/{lib_id}").status_code == 200
    assert client.get(f"/api/libraries/{lib_id}/filter/summary").status_code == 404
    assert client.get(f"/api/libraries/{lib_id}/stats").status_code == 404
    assert client.get("/api/libraries").json() == []
    assert client.get(f"/api/photos?library_id={lib_id}").json()["items"] == []
    with client.app.state.db.connect() as c:
        for table in ("photos", "review_labels", "duplicate_picks", "duplicate_groups"):
            assert c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert list(settings.thumbnails_dir.rglob("*.jpg")) == []
