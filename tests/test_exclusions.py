"""Pre-scan exclusions (ADR-016): excluded files are never read, analyzed or modified."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.ingest.pipeline as pipeline_mod
from app.core.config import Settings
from app.ingest.scanner import exclusion_key, normalize_exclusion, scan_folder
from app.main import create_app
from tests.conftest import fingerprint

SUB = "יום הולדת"


def _jpeg(path: Path, seed: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.effect_noise((320, 240), 20 + seed * 7).convert("RGB").resize((640, 480)).save(path, "JPEG", quality=90)
    return path


@pytest.fixture
def tree(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "תמונות"
    files = {
        "keep1": _jpeg(root / "a.jpg", 1),
        "keep2": _jpeg(root / SUB / "b.jpg", 2),
        "skip1": _jpeg(root / "c.jpg", 3),
        "skip2": _jpeg(root / SUB / "תמונה ד.JPG", 4),
    }
    (root / "clip.mp4").write_bytes(b"not really a video")
    files["video"] = root / "clip.mp4"
    return {"root": root, **files}


@pytest.fixture
def client(tmp_path: Path, tree):
    s = Settings(_env_file=None, data_dir=tmp_path / "data", ingest_workers=1,
                 allowed_hosts=["testserver"], browse_roots=[tmp_path])
    with TestClient(create_app(s)) as c:
        yield c


@pytest.fixture
def spy(monkeypatch):
    """Records every file the pipeline analyzes and every Path.stat() call."""
    analyzed: list[str] = []
    stats: list[str] = []
    real_analyze = pipeline_mod.analyze_file
    real_stat = Path.stat

    def analyze(path, config):
        analyzed.append(os.path.normcase(str(path)))
        return real_analyze(path, config)

    def stat(self, *a, **k):
        stats.append(os.path.normcase(str(self)))
        return real_stat(self, *a, **k)

    monkeypatch.setattr(pipeline_mod, "analyze_file", analyze)
    monkeypatch.setattr(Path, "stat", stat)
    return {"analyzed": analyzed, "stats": stats}


def _norm(p: Path) -> str:
    return os.path.normcase(str(p))  # not p.resolve(): that calls Path.stat() and would pollute the spy


def _scan(client, root, exclude=None):
    body = {"path": str(root)}
    if exclude is not None:
        body["exclude"] = exclude
    r = client.post("/api/libraries", json=body)
    assert r.status_code == 201, r.text
    res = r.json()
    job = client.app.state.jobs.wait(res["job"]["id"], timeout=120)
    assert job["status"] == "done", job
    return res["library"]["id"], job


def _rescan(client, lib_id):
    job = client.post(f"/api/libraries/{lib_id}/scan").json()
    job = client.app.state.jobs.wait(job["id"], timeout=120)
    assert job["status"] == "done", job
    return job


def _statuses(client, lib_id) -> dict[str, str]:
    with client.app.state.db.connect() as c:
        return {r[0]: r[1] for r in c.execute("SELECT rel_path, status FROM photos WHERE library_id = ?", (lib_id,))}


def test_excluded_files_are_never_read_analyzed_or_modified(client, tree, spy):
    before = fingerprint(tree["root"])
    spy["stats"].clear()  # fingerprint() itself stats every file
    lib_id, job = _scan(client, tree["root"], [str(tree["skip1"]), str(tree["skip2"]), str(tree["video"])])
    for key in ("skip1", "skip2"):
        assert _norm(tree[key]) not in spy["analyzed"]
        assert _norm(tree[key]) not in spy["stats"]
    assert {_norm(tree["keep1"]), _norm(tree["keep2"])} <= set(spy["analyzed"])
    assert job["stats"]["excluded"] == 2 and job["stats"]["files_found"] == 2
    assert _statuses(client, lib_id) == {"a.jpg": "ok", f"{SUB}/b.jpg": "ok"}
    assert fingerprint(tree["root"]) == before  # originals untouched, nothing added or removed
    assert client.get(f"/api/libraries/{lib_id}/stats").json()["stats"]["exclusions"] == 3


def test_rescan_keeps_exclusions_and_unexclude_brings_photo_back(client, tree, spy):
    lib_id, _ = _scan(client, tree["root"], [str(tree["skip1"])])
    spy["analyzed"].clear()
    job = _rescan(client, lib_id)
    assert job["stats"]["excluded"] == 1
    assert _norm(tree["skip1"]) not in spy["analyzed"]
    assert "c.jpg" not in _statuses(client, lib_id)
    # Choosing the folder again without the mark = un-exclude; the next scan indexes it.
    lib_again, _ = _scan(client, tree["root"], [])
    assert lib_again == lib_id
    assert _statuses(client, lib_id)["c.jpg"] == "ok"


def test_path_typed_by_hand_keeps_existing_exclusions(client, tree):
    lib_id, _ = _scan(client, tree["root"], [str(tree["skip1"])])
    _scan(client, tree["root"])  # no "exclude" field at all
    assert "c.jpg" not in _statuses(client, lib_id)
    assert client.get("/api/exclusions").json()[0]["paths"] == [str(tree["skip1"].resolve())]


def test_indexed_then_excluded_becomes_excluded_not_missing(client, tree):
    lib_id, _ = _scan(client, tree["root"])
    thumbs = client.app.state.settings.thumbnails_dir
    with client.app.state.db.connect() as c:
        thumb = c.execute("SELECT thumbnail_path FROM photos WHERE rel_path = 'c.jpg'").fetchone()[0]
    assert (thumbs / thumb).is_file()
    _scan(client, tree["root"], ["c.jpg"])  # relative form is accepted too
    st = _statuses(client, lib_id)
    assert st["c.jpg"] == "excluded" and "missing" not in st.values()
    assert not (thumbs / thumb).exists()  # derived thumbnail released; original still there
    assert tree["skip1"].is_file()
    stats = client.get(f"/api/libraries/{lib_id}/stats").json()["stats"]
    assert stats["missing"] == 0 and stats["excluded_indexed"] == 1
    photos = client.get("/api/photos", params={"library_id": lib_id}).json()["items"]
    assert "c.jpg" not in {p["rel_path"] for p in photos}
    # Un-exclude → analyzed again on the next scan.
    _scan(client, tree["root"], [])
    assert _statuses(client, lib_id)["c.jpg"] == "ok"


def test_deleted_file_that_is_no_longer_excluded_becomes_missing(client, tree):
    lib_id, _ = _scan(client, tree["root"])
    _scan(client, tree["root"], ["c.jpg"])
    tree["skip1"].unlink()
    _scan(client, tree["root"], [])
    assert _statuses(client, lib_id)["c.jpg"] == "missing"


@pytest.mark.parametrize("bad", [
    "../outside.jpg",
    "sub/../../x.jpg",
    "notes.txt",
    "a.jpg:stream",
    "",
])
def test_invalid_exclusions_rejected(client, tree, bad):
    r = client.post("/api/libraries", json={"path": str(tree["root"]), "exclude": [bad], "scan": False})
    assert r.status_code == 400, r.text
    assert client.get("/api/libraries").json() == []  # nothing created on a bad request


def test_exclusion_outside_root_rejected(client, tree, tmp_path):
    other = _jpeg(tmp_path / "other" / "x.jpg", 9)
    r = client.post("/api/libraries", json={"path": str(tree["root"]), "exclude": [str(other)], "scan": False})
    assert r.status_code == 400


@pytest.mark.skipif(sys.platform != "win32", reason="Windows paths are case-insensitive")
def test_exclusion_match_is_case_insensitive_on_windows(tree):
    skipped: list[Path] = []
    files = scan_folder(tree["root"], {exclusion_key(f"{SUB.upper()}/תמונה ד.jpg"), exclusion_key("C.JPG")}, skipped)
    names = {f.path.name for f in files}
    assert names == {"a.jpg", "b.jpg"} and len(skipped) == 2


def test_normalize_exclusion(tree):
    root = tree["root"]
    assert normalize_exclusion(root, str(root / SUB / "b.jpg")) == f"{SUB}/b.jpg"
    assert normalize_exclusion(root, "clip.mp4") == "clip.mp4"  # videos can be excluded too
    for bad in ("..\\x.jpg", "x.txt", "\x00.jpg"):
        with pytest.raises(ValueError):
            normalize_exclusion(root, bad)


def test_summary_counts_recursively(client, tree):
    r = client.post("/api/browse/summary", json={
        "path": str(tree["root"]),
        "exclude": [str(tree["skip1"]), str(tree["skip2"]), str(tree["video"]), str(tree["root"] / "gone.jpg")],
    })
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["images"], b["excluded_images"], b["images_to_scan"]) == (4, 2, 2)
    assert (b["videos"], b["excluded_videos"]) == (1, 1)  # gone.jpg does not exist → not counted


def test_listing_items_carry_path(client, tree):
    items = client.get("/api/browse", params={"path": str(tree["root"])}).json()["items"]
    assert {Path(i["path"]).name for i in items} == {"a.jpg", "c.jpg", "clip.mp4"}
