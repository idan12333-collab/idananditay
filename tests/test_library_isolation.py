"""Regression: a photo from a previously scanned folder must never be shown for another folder.

Bug found on real photos (2026-09-26): folder B with one photo displayed folder A's photo.
Root cause: SQLite reused deleted row IDs, so B's photo got A's old ID and therefore the
same image URL (/api/photos/1/thumbnail), which the browser served from its HTTP cache.
"""

from __future__ import annotations

import io
import sqlite3

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.db.database import SCHEMA, SCHEMA_VERSION, Database
from app.main import create_app
from tests.conftest import fingerprint

RED = (220, 30, 30)
BLUE = (30, 30, 220)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def _single_photo_folder(root, name: str, color) -> None:
    root.mkdir(parents=True)
    rng = np.random.default_rng(sum(color))
    arr = np.clip(np.array(color, dtype=np.int16) + rng.integers(-20, 20, (600, 800, 3)), 0, 255)
    Image.fromarray(arr.astype(np.uint8)).save(root / name, quality=92)


def _scan(client, root) -> int:
    res = client.post("/api/libraries", json={"path": str(root)})
    assert res.status_code == 201, res.text
    job = client.app.state.jobs.wait(res.json()["job"]["id"], timeout=120)
    assert job["status"] == "done", job
    return res.json()["library"]["id"]


def _only_photo(client, lib_id: int) -> dict:
    page = client.get("/api/photos", params={"library_id": lib_id}).json()
    assert page["total"] == 1, page
    return page["items"][0]


def _dominant(client, url: str) -> str:
    r = client.get(url)
    assert r.status_code == 200
    mean = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"), dtype=np.float32).mean(axis=(0, 1))
    return "red" if mean[0] > mean[2] else "blue"


@pytest.mark.parametrize("delete_first", [True, False], ids=["delete-A-then-scan-B", "switch-A-to-B"])
def test_folder_b_never_displays_folder_a_image(client, tmp_path, delete_first):
    folder_a, folder_b = tmp_path / "A", tmp_path / "B"
    _single_photo_folder(folder_a, "IMG_0001.jpg", RED)
    _single_photo_folder(folder_b, "IMG_0001.jpg", BLUE)  # same file name on purpose
    before = fingerprint(folder_a) | fingerprint(folder_b)

    lib_a = _scan(client, folder_a)
    photo_a = _only_photo(client, lib_a)
    # What a browser would now hold in its HTTP cache for folder A.
    cached_urls = {photo_a["thumbnail_url"], photo_a["preview_url"]}
    assert _dominant(client, photo_a["thumbnail_url"]) == "red"

    if delete_first:
        assert client.delete(f"/api/libraries/{lib_a}").status_code == 200
    lib_b = _scan(client, folder_b)
    photo_b = _only_photo(client, lib_b)

    # Record is tied to folder B's absolute path, not A's.
    assert lib_b != lib_a
    assert photo_b["library_id"] == lib_b
    assert photo_b["source_path"] == str((folder_b / "IMG_0001.jpg").resolve())
    assert photo_b["id"] != photo_a["id"]  # IDs are never reused
    assert photo_b["content_hash"] != photo_a["content_hash"]
    assert photo_b["thumbnail_path"] != photo_a["thumbnail_path"]

    # No URL of B can hit a browser cache entry created for A.
    assert not {photo_b["thumbnail_url"], photo_b["preview_url"]} & cached_urls

    # The bytes served for B are B's image.
    assert _dominant(client, photo_b["thumbnail_url"]) == "blue"
    assert _dominant(client, photo_b["preview_url"]) == "blue"
    detail = client.get(f"/api/photos/{photo_b['id']}").json()
    assert detail["source_path"] == photo_b["source_path"]
    assert _dominant(client, detail["thumbnail_url"]) == "blue"

    if not delete_first:  # A is still intact and still shows only A.
        assert _only_photo(client, lib_a)["source_path"] == str((folder_a / "IMG_0001.jpg").resolve())

    assert fingerprint(folder_a) | fingerprint(folder_b) == before  # originals untouched


def test_image_urls_are_versioned_by_content(client, tmp_path):
    folder = tmp_path / "A"
    _single_photo_folder(folder, "p.jpg", RED)
    photo = _only_photo(client, _scan(client, folder))
    version = photo["content_hash"][:16]
    assert photo["thumbnail_url"].endswith(f"?v={version}")
    assert photo["preview_url"].endswith(f"?v={version}")

    r = client.get(photo["thumbnail_url"])
    assert "immutable" in r.headers["cache-control"]
    assert r.headers["etag"] == f'"{photo["content_hash"]}"'
    # An unversioned or outdated URL must never be cached long-term.
    for url in (f"/api/photos/{photo['id']}/thumbnail", f"/api/photos/{photo['id']}/thumbnail?v=0000"):
        assert client.get(url).headers["cache-control"] == "no-cache"
    # JSON API responses are never cached by the browser.
    assert client.get("/api/photos", params={"library_id": photo["library_id"]}).headers["cache-control"] == "no-store"


def test_rescan_after_file_replaced_changes_url(client, tmp_path):
    """Same path, new content (user replaced the file): the old image must not be served from cache."""
    folder = tmp_path / "A"
    _single_photo_folder(folder, "p.jpg", RED)
    lib = _scan(client, folder)
    old = _only_photo(client, lib)
    (folder / "p.jpg").unlink()
    _single_photo_folder(tmp_path / "tmp", "p.jpg", BLUE)
    (tmp_path / "tmp" / "p.jpg").replace(folder / "p.jpg")
    job = client.app.state.jobs.wait(client.post(f"/api/libraries/{lib}/scan").json()["id"], timeout=120)
    assert job["status"] == "done"
    new = _only_photo(client, lib)
    assert new["thumbnail_url"] != old["thumbnail_url"]
    assert _dominant(client, new["thumbnail_url"]) == "blue"


def test_migration_from_v1_keeps_data_and_stops_id_reuse(tmp_path):
    path = tmp_path / "old.sqlite3"
    v1 = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INTEGER PRIMARY KEY")
    with sqlite3.connect(path) as c:
        c.executescript(v1)
        c.execute("INSERT INTO meta VALUES('schema_version', '1')")
        c.execute("INSERT INTO libraries(id, root_path, name, created_at) VALUES(1, 'C:/A', 'A', 'x'), (2, 'C:/B', 'B', 'x')")
        c.execute("INSERT INTO duplicate_groups(id, library_id, kind, size) VALUES(1, 2, 'exact', 2)")
        c.execute("INSERT INTO photos(id, library_id, source_path, rel_path, status, duplicate_group_id) "
                  "VALUES(5, 2, 'C:/B/x.jpg', 'x.jpg', 'ok', 1)")
    db = Database(path)
    db.initialize()
    with db.connect() as c:
        assert c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == str(SCHEMA_VERSION)
        assert [tuple(r) for r in c.execute("SELECT id, library_id, duplicate_group_id FROM photos")] == [(5, 2, 1)]
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in ("libraries", "photos", "duplicate_groups"):
            ddl = c.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0]
            assert "AUTOINCREMENT" in ddl, table
        c.execute("DELETE FROM photos")
        c.execute("DELETE FROM libraries WHERE id = 2")
        new_id = c.execute("INSERT INTO libraries(root_path, name, created_at) VALUES('C:/C', 'C', 'x')").lastrowid
    assert new_id == 3  # not 2 again
    db.initialize()  # idempotent
