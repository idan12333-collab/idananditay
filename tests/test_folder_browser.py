"""In-app folder browser (ADR-014): listing, paging, thumbnails, safety and read-only guarantees."""

from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services import folder_browser as fb
from tests.conftest import fingerprint

HEB = "תמונות משפחה"


def _jpeg(path: Path, color=(200, 80, 40), size=(900, 600)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, "JPEG", quality=90)
    return path


@pytest.fixture
def tree(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "allowed"
    fam = root / HEB
    _jpeg(fam / "יום הולדת.jpg")
    _jpeg(fam / "b.JPG", (10, 120, 220))
    Image.new("RGBA", (300, 200), (0, 200, 0, 128)).save(fam / "c.png")
    (fam / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42 not a real video")
    (fam / "notes.txt").write_text("secret", encoding="utf-8")
    (fam / "desktop.ini").write_text("[x]", encoding="utf-8")
    (fam / ".hidden").mkdir()
    _jpeg(fam / ".hidden" / "h.jpg")
    _jpeg(fam / "2019 טיול" / "d.jpg")
    outside = _jpeg(tmp_path / "outside" / "secret.jpg")
    return {"root": root, "fam": fam, "outside": outside}


@pytest.fixture
def client(tmp_path: Path, tree):
    s = Settings(_env_file=None, data_dir=tmp_path / "data", ingest_workers=1,
                 allowed_hosts=["testserver"], browse_roots=[tree["root"]])
    with TestClient(create_app(s)) as c:
        yield c


def _ls(client, path, **params):
    return client.get("/api/browse", params={"path": str(path), **params})


def test_lists_folders_images_and_videos_with_hebrew_names(client, tree):
    r = _ls(client, tree["fam"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["counts"] == {"folders": 1, "images": 3, "videos": 1, "cloud_only": 0}
    assert [f["name"] for f in body["folders"]] == ["2019 טיול"]  # .hidden is not shown
    names = {i["name"]: i for i in body["items"]}
    assert set(names) == {"יום הולדת.jpg", "b.JPG", "c.png", "clip.mp4"}  # no .txt / .ini
    assert names["clip.mp4"]["kind"] == "video" and names["clip.mp4"]["thumbnail_url"] is None
    assert names["יום הולדת.jpg"]["kind"] == "image" and names["יום הולדת.jpg"]["thumbnail_url"]
    assert [c["name"] for c in body["breadcrumbs"]][-1] == HEB
    assert body["parent"] == str(tree["root"].resolve())
    # Navigating into a Hebrew-named subfolder via the returned path works.
    sub = _ls(client, body["folders"][0]["path"]).json()
    assert sub["counts"]["images"] == 1


def test_root_has_no_parent_and_roots_endpoint(client, tree):
    assert _ls(client, tree["root"]).json()["parent"] is None
    locs = client.get("/api/browse/roots").json()["locations"]
    assert {"label": str(tree["root"].resolve()), "kind": "drive", "path": str(tree["root"].resolve())} in locs


def test_pagination(client, tree):
    big = tree["root"] / "big"
    for i in range(25):
        _jpeg(big / f"p{i:03d}.jpg", size=(64, 64))
    seen = []
    for offset in (0, 10, 20):
        body = _ls(client, big, offset=offset, limit=10).json()
        assert body["total"] == 25 and body["offset"] == offset
        seen += [i["name"] for i in body["items"]]
    assert seen == [f"p{i:03d}.jpg" for i in range(25)]
    assert _ls(client, big, limit=100000).status_code == 422  # page size is capped


def test_thumbnail_is_small_jpeg_and_originals_untouched(client, tree):
    before = fingerprint(tree["root"])
    items = _ls(client, tree["fam"]).json()["items"]
    for it in items:
        if it["thumbnail_url"]:
            r = client.get(it["thumbnail_url"])
            assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
            assert "immutable" in r.headers["cache-control"]  # listing version == file version
            with Image.open(BytesIO(r.content)) as im:
                assert max(im.size) <= fb.BROWSE_THUMB_SIDE
    assert fingerprint(tree["root"]) == before
    # Nothing is written next to the photos.
    assert sorted(p.name for p in tree["fam"].iterdir()) == sorted(
        ["יום הולדת.jpg", "b.JPG", "c.png", "clip.mp4", "notes.txt", "desktop.ini", ".hidden", "2019 טיול"])


def test_changed_file_gets_new_url(client, tree):
    p = tree["fam"] / "b.JPG"
    url1 = next(i for i in _ls(client, tree["fam"]).json()["items"] if i["name"] == "b.JPG")["thumbnail_url"]
    _jpeg(p, (0, 0, 0), size=(500, 500))
    os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 5_000_000_000))
    url2 = next(i for i in _ls(client, tree["fam"]).json()["items"] if i["name"] == "b.JPG")["thumbnail_url"]
    assert url1 != url2
    assert client.get(url1).headers["cache-control"] == "no-cache"  # stale URL is never cached


def test_non_images_are_never_decoded(client, tree, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("decode must not be called")

    monkeypatch.setattr(fb, "decode_preview", boom)
    for name in ("notes.txt", "clip.mp4", "desktop.ini"):
        r = client.get("/api/browse/thumbnail", params={"path": str(tree["fam"] / name)})
        assert r.status_code == 415, (name, r.text)
    # Rejected by extension before touching the disk (the file does not even exist).
    assert client.get("/api/browse/thumbnail", params={"path": str(tree["fam"] / "ghost.txt")}).status_code == 415


def test_listing_never_stats_non_media_files(client, tree, monkeypatch):
    stat_calls: list[str] = []
    real_scandir = os.scandir

    class Entry:
        def __init__(self, e):
            self._e, self.name, self.path = e, e.name, e.path

        def is_dir(self, **k):
            return self._e.is_dir(**k)

        def stat(self, **k):
            stat_calls.append(self.name)
            return self._e.stat(**k)

    monkeypatch.setattr(os, "scandir", lambda p: [Entry(e) for e in real_scandir(p)])
    assert _ls(client, tree["fam"]).status_code == 200
    assert "notes.txt" not in stat_calls and "desktop.ini" not in stat_calls
    assert "clip.mp4" in stat_calls  # media files are stat-ed (size), never opened


@pytest.mark.parametrize("make_path", [
    lambda t: t["outside"],                                     # absolute path outside the roots
    lambda t: t["root"] / ".." / "outside" / "secret.jpg",      # traversal with ..
    lambda t: t["outside"].parent,                              # folder outside the roots
])
def test_outside_roots_refused(client, tree, make_path):
    p = make_path(tree)
    assert _ls(client, p).status_code in (400, 403)
    if p.suffix:
        assert client.get("/api/browse/thumbnail", params={"path": str(p)}).status_code == 403


@pytest.mark.parametrize("raw,status", [
    ("relative\\folder", 400),
    ("..\\..\\Windows", 400),
    ("", 400),
    ("C:\\x\\a.jpg:secret", 400),         # NTFS alternate data stream
    ("C:\\x\\a\x00.jpg", 400),
    ("\\\\server\\share\\a.jpg", 403),    # UNC / network
    ("\\\\?\\C:\\Windows\\a.jpg", 403),   # device path
    ("//server/share/a.jpg", 403),
])
@pytest.mark.skipif(sys.platform != "win32", reason="Windows path rules")
def test_malformed_paths_refused(client, raw, status):
    assert _ls(client, raw).status_code == status
    assert client.get("/api/browse/thumbnail", params={"path": raw}).status_code in (status, 415)


def test_missing_folder_404(client, tree):
    assert _ls(client, tree["root"] / "nope").status_code == 404


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junctions")
def test_junction_pointing_outside_is_refused(client, tree):
    import _winapi

    link = tree["root"] / "escape"
    try:
        _winapi.CreateJunction(str(tree["outside"].parent), str(link))
    except OSError:
        pytest.skip("cannot create junction")
    assert _ls(client, link).status_code == 403
    assert client.get("/api/browse/thumbnail", params={"path": str(link / "secret.jpg")}).status_code == 403


def test_cloud_only_files_are_not_downloaded(client, tree, monkeypatch):
    real = fb._attributes

    def fake(st):
        return fb.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS if st.st_size == cloud_size else real(st)

    cloud = tree["fam"] / "b.JPG"
    Image.effect_noise((731, 419), 60).convert("RGB").save(cloud, "JPEG")  # unique file size
    cloud_size = cloud.stat().st_size
    monkeypatch.setattr(fb, "_attributes", fake)
    monkeypatch.setattr(fb, "decode_preview", lambda *a, **k: (_ for _ in ()).throw(AssertionError("opened")))
    body = _ls(client, tree["fam"]).json()
    item = next(i for i in body["items"] if i["name"] == "b.JPG")
    assert item["cloud_only"] is True and item["thumbnail_url"] is None
    assert body["counts"]["cloud_only"] == 1
    r = client.get("/api/browse/thumbnail", params={"path": str(cloud)})
    assert r.status_code == 409


def test_cross_site_requests_refused(client, tree):
    url = f"/api/browse?path={quote(str(tree['fam']))}"
    assert client.get(url, headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.get(url, headers={"sec-fetch-site": "same-site"}).status_code == 403
    assert client.get(url, headers={"sec-fetch-site": "same-origin"}).status_code == 200


def test_cloud_attribute_mask():
    assert fb.is_cloud_only(fb.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)
    assert fb.is_cloud_only(fb.FILE_ATTRIBUTE_OFFLINE)
    assert not fb.is_cloud_only(0x20)  # archive attribute only = local file
