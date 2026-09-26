import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import fingerprint


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def _scan(client, root):
    res = client.post("/api/libraries", json={"path": str(root)})
    assert res.status_code == 201, res.text
    body = res.json()
    job = client.app.state.jobs.wait(body["job"]["id"], timeout=120)
    assert job["status"] == "done", job
    return body["library"]["id"], job


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert ".heic" in body["supported_extensions"]


def test_index_page_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "AI Photo Album" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_rejects_foreign_host_header(client):
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_invalid_folder(client, tmp_path):
    r = client.post("/api/libraries", json={"path": str(tmp_path / "does-not-exist")})
    assert r.status_code == 400


def test_scan_browse_and_delete(client, library, settings):
    root, _ = library
    before = fingerprint(root)
    lib_id, job = _scan(client, root)
    assert job["stats"]["files_found"] == 11
    assert job["stats"]["seconds_per_1000"] is not None

    libs = client.get("/api/libraries").json()
    assert libs[0]["photo_count"] == 10

    stats = client.get(f"/api/libraries/{lib_id}/stats").json()["stats"]
    assert stats["redundant_duplicates"] == 2

    page = client.get("/api/photos", params={"library_id": lib_id, "limit": 3}).json()
    assert page["total"] == 10 and len(page["items"]) == 3
    unique = client.get("/api/photos", params={"library_id": lib_id, "filter": "unique"}).json()
    assert unique["total"] == 8
    y2019 = client.get("/api/photos", params={"library_id": lib_id, "year": 2019}).json()
    assert y2019["total"] >= 1
    assert client.get("/api/photos", params={"library_id": lib_id, "filter": "bogus"}).status_code == 400

    photo = page["items"][0]
    detail = client.get(f"/api/photos/{photo['id']}").json()
    assert "signals" in detail and "duplicates" in detail
    thumb = client.get(photo["thumbnail_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    preview = client.get(photo["preview_url"])
    assert preview.status_code == 200 and preview.content[:2] == b"\xff\xd8"

    dups = client.get(f"/api/libraries/{lib_id}/duplicates").json()
    assert dups["total"] == 1 and len(dups["groups"][0]["members"]) == 3

    # Rescan is incremental.
    job2 = client.app.state.jobs.wait(client.post(f"/api/libraries/{lib_id}/scan").json()["id"], timeout=120)
    assert job2["stats"]["skipped_unchanged"] == 10

    # Deleting derived data removes thumbnails but never originals.
    thumbs_before = list(settings.thumbnails_dir.rglob("*.jpg"))
    assert thumbs_before
    r = client.delete(f"/api/libraries/{lib_id}")
    assert r.status_code == 200 and r.json()["thumbnails_removed"] == len(thumbs_before)
    assert list(settings.thumbnails_dir.rglob("*.jpg")) == []
    assert client.get("/api/libraries").json() == []
    assert fingerprint(root) == before


def test_index_embeds_build_in_asset_urls(client):
    """A new build must produce new app.js/styles.css URLs, so a browser can never run an old
    cached script inside a new page, and the page can detect that the server was updated (ADR-015)."""
    from app.core.instance import BUILD_ID

    html = client.get("/").text
    assert "__BUILD__" not in html
    assert f'/static/app.js?v={BUILD_ID}' in html
    assert f'/static/styles.css?v={BUILD_ID}' in html
    assert f'<meta name="app-build" content="{BUILD_ID}">' in html
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert client.get("/api/health").json()["build"] == BUILD_ID
