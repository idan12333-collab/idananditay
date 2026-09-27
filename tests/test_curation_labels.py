"""Curation labels (ADR-022): schema v5 migration, repository, quick-labeling API.

The key invariant: a curation label never changes the filter (filtered/kept) or review_stats.
"""

from __future__ import annotations

import csv
import io
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db.database import SCHEMA_VERSION, Database
from app.main import create_app


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
    return lib_id, client.get(f"/api/photos?library_id={lib_id}&limit=500").json()["items"]


def _filter_ids(client, lib_id):
    return {name: sorted(p["id"] for p in client.get(f"/api/photos?library_id={lib_id}&filter={name}&limit=500").json()["items"])
            for name in ("filtered", "kept", "unreviewed")}


# ------------------------------------------------------------------ migration
def test_v4_to_v5_migration_keeps_data_and_backs_up(tmp_path):
    path = tmp_path / "data" / "library.sqlite3"
    Database(path).initialize()
    with sqlite3.connect(path) as c:  # simulate a v4 database: no v5 tables, version 4
        c.execute("DROP TABLE curation_labels")
        c.execute("DROP TABLE ai_label_proposals")
        c.execute("UPDATE meta SET value = '4' WHERE key = 'schema_version'")
        c.execute("INSERT INTO libraries(root_path, name, created_at) VALUES('C:/x', 'x', 'now')")
        c.execute("INSERT INTO review_labels(content_hash, verdict, created_at, updated_at) VALUES('h', 'good', 'n', 'n')")
    db = Database(path)
    db.initialize()  # additive: no migration step reported, but the backup runs
    assert SCHEMA_VERSION == 5
    assert db.last_backup is not None and db.last_backup.parent == path.parent / "backups"
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT name FROM libraries").fetchall() == [("x",)]
        assert c.execute("SELECT verdict FROM review_labels").fetchall() == [("good",)]
        assert c.execute("SELECT COUNT(*) FROM curation_labels").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM ai_label_proposals").fetchone()[0] == 0
    with sqlite3.connect(db.last_backup) as c:  # the backup is the v4 database, untouched
        assert c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == "4"
        assert c.execute("SELECT name FROM sqlite_master WHERE name='curation_labels'").fetchone() is None
    assert Database(path).initialize() == []  # a normal start afterwards: no migration, no backup


# ----------------------------------------------------------------- repository
def test_repository_upsert_delete(repo):
    photo = {"id": 1, "content_hash": "abc", "rel_path": "a.jpg", "capture_time": "2020-01-01T10:00:00"}
    first = repo.set_curation_label(photo, "maybe", special=False, stratum="random_kept", held_out=True)
    assert first["worthiness"] == "maybe" and first["source"] == "owner" and first["blind"] == 1 and first["held_out"] == 1
    second = repo.set_curation_label(photo, "must", special=True)
    assert second["worthiness"] == "must" and second["special"] == 1 and second["stratum"] == "random_kept"
    assert second["created_at"] == first["created_at"]
    with pytest.raises(ValueError):
        repo.set_curation_label(photo, "great")
    with pytest.raises(ValueError):
        repo.set_curation_label({"id": 2}, "no")
    repo.set_curation_label({"id": 2, "content_hash": "def"}, "no")
    assert repo.seed_progress([{"content_hash": "abc", "stratum": "a"}, {"content_hash": "zzz", "stratum": "a"}]) == \
        {"total": 2, "labeled": 1, "strata": {"a": {"total": 2, "labeled": 1}}}
    assert repo.delete_curation_label("abc") and not repo.delete_curation_label("abc")
    assert repo.delete_all_curation_labels() == 1
    assert repo.get_curation_label("def") is None


# ------------------------------------------------------------------------ API
def test_quick_labeling_flow(client, scanned, settings):
    lib, photos = scanned
    before = _filter_ids(client, lib)
    review_before = client.get(f"/api/libraries/{lib}/review/stats").json()

    r = client.get(f"/api/libraries/{lib}/seed")
    assert r.status_code == 404 and "מדגם" in r.json()["detail"]
    created = client.post(f"/api/libraries/{lib}/seed")
    assert created.status_code == 201
    assert client.post(f"/api/libraries/{lib}/seed").status_code == 409  # never replaced
    assert (settings.data_dir / "seed" / f"seed_sample_lib{lib}.json").exists()

    s = client.get(f"/api/libraries/{lib}/seed").json()
    total = s["progress"]["total"]
    assert total > 0 and s["progress"]["labeled"] == 0 and s["item"]["index"] == 0
    assert set(s["item"]) == {"index", "photo_id", "stratum", "preview_url", "label"}  # blind: no scores/flags

    seen = []
    for w in ["must", "maybe", "no"] * total:
        item = client.get(f"/api/libraries/{lib}/seed").json()["item"]
        if item is None:
            break
        seen.append(item["photo_id"])
        body = client.put(f"/api/photos/{item['photo_id']}/curation", json={"worthiness": w, "special": w == "must"}).json()
        assert body["worthiness"] == w and body["stratum"] == item["stratum"]
    done = client.get(f"/api/libraries/{lib}/seed").json()
    assert done["done"] and done["item"] is None and done["progress"]["labeled"] == total == len(set(seen))

    # going back shows the earlier label, and it can be changed
    back = client.get(f"/api/libraries/{lib}/seed?index=0").json()["item"]
    assert back["label"]["worthiness"] == "must" and back["label"]["special"] == 1
    client.put(f"/api/photos/{back['photo_id']}/curation", json={"worthiness": "no"})
    assert client.get(f"/api/libraries/{lib}/seed?index=0").json()["item"]["label"]["worthiness"] == "no"
    assert client.get(f"/api/libraries/{lib}/seed?index=9999").json()["item"]["index"] == total - 1

    # the filter and the technical review are untouched
    assert _filter_ids(client, lib) == before
    assert client.get(f"/api/libraries/{lib}/review/stats").json() == review_before

    # export
    res = client.get(f"/api/libraries/{lib}/curation/export")
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(res.text.lstrip("\ufeff"))))
    assert len(rows) == total and {"worthiness", "special", "held_out", "filtered", "filter_reason"} <= set(rows[0])

    # delete one label → it's the next unlabeled again
    assert client.delete(f"/api/photos/{back['photo_id']}/curation").json() == {"deleted": True}
    assert client.get(f"/api/libraries/{lib}/seed").json()["item"]["photo_id"] == back["photo_id"]


def test_nominate(client, scanned):
    lib, photos = scanned
    pid = photos[0]["id"]
    assert client.post(f"/api/photos/{pid}/nominate").status_code == 404  # no sample yet
    client.post(f"/api/libraries/{lib}/seed")
    total = client.get(f"/api/libraries/{lib}/seed").json()["progress"]["total"]
    ok = [p for p in photos if p["status"] == "ok"]
    results = [client.post(f"/api/photos/{p['id']}/nominate").json()["added"] for p in ok]
    after = client.get(f"/api/libraries/{lib}/seed").json()["progress"]
    assert after["total"] == total + sum(results)
    assert all(not client.post(f"/api/photos/{p['id']}/nominate").json()["added"] for p in ok)  # idempotent


def test_curation_errors(client, scanned):
    lib, photos = scanned
    pid = next(p["id"] for p in photos if p["status"] == "ok")
    assert client.put(f"/api/photos/{pid}/curation", json={"worthiness": "great"}).status_code == 400
    assert client.put(f"/api/photos/{pid}/curation", json={}).status_code == 422
    assert client.put("/api/photos/99999/curation", json={"worthiness": "no"}).status_code == 404
    assert client.get("/api/libraries/999/seed").status_code == 404
    assert client.delete(f"/api/photos/{pid}/curation").json() == {"deleted": False}
    empty = client.get(f"/api/libraries/{lib}/curation/export")
    assert empty.status_code == 200 and empty.text.lstrip("\ufeff").startswith("photo_id,")


def test_skip_and_missing_originals(client, scanned, settings):
    """Owner bug 2026-09-26: files replaced after the scan showed black, and there was no way to skip."""
    lib, photos = scanned
    client.post(f"/api/libraries/{lib}/seed")
    s = client.get(f"/api/libraries/{lib}/seed").json()
    total = s["progress"]["total"]
    assert total >= 3
    # skip item 0 (no label), label item 1 → the next item is 2, not the skipped 0
    item1 = client.get(f"/api/libraries/{lib}/seed?index=1").json()["item"]
    client.put(f"/api/photos/{item1['photo_id']}/curation", json={"worthiness": "maybe"})
    nxt = client.get(f"/api/libraries/{lib}/seed?after=1").json()["item"]
    assert nxt["index"] == 2
    assert client.get(f"/api/libraries/{lib}/seed").json()["item"]["index"] == 0  # skipped ones come back later
    assert client.get(f"/api/libraries/{lib}/seed?after={total - 1}").json()["item"]["index"] == 0  # wrap around

    # an original deleted after the scan is skipped (not shown black) and reported
    item0 = client.get(f"/api/libraries/{lib}/seed?index=0").json()["item"]
    src = client.get(f"/api/photos/{item0['photo_id']}").json()["source_path"]
    import os
    os.remove(src)
    after = client.get(f"/api/libraries/{lib}/seed").json()
    assert after["progress"]["missing"] == 1 and after["progress"]["total"] == total - 1
    assert after["item"]["photo_id"] != item0["photo_id"]

    # a new sample can replace the old one; the old file is kept, labels survive, the missing file is not sampled
    assert client.post(f"/api/libraries/{lib}/seed").status_code == 409
    r = client.post(f"/api/libraries/{lib}/seed?replace=true")
    assert r.status_code == 201 and r.json()["progress"]["missing"] == 0
    assert (settings.data_dir / "seed" / f"seed_sample_lib{lib}.bak").exists()
    assert client.get(f"/api/libraries/{lib}/curation/export").text.count("\n") >= 2  # header + the label
