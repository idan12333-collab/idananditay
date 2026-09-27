"""Seed sample for quick labeling (ADR-022): determinism, strata, held-out rate, small libraries, CLI."""

from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from app.curation import seed as seed_sample
from app.curation.seed import _allocate, build_sample, is_held_out, nominate


@pytest.fixture(autouse=True)
def _files_exist(monkeypatch):
    """The synthetic library below has no files on disk."""
    monkeypatch.setattr(seed_sample, "original_exists", lambda photo: True)


def _h(i: int) -> str:
    return hashlib.sha256(f"photo-{i}".encode()).hexdigest()


def _synthetic_library(repo, n_kept=400, n_blurry=40, n_screens=25, n_dark=5, n_groups=40) -> int:
    """A library written straight into the DB: kept photos over 24 months + filtered ones + dup groups."""
    lib = repo.create_library("C:/synthetic", "synthetic")["id"]
    rows, i = [], 0

    def photo(**kw):
        nonlocal i
        i += 1
        month = (i % 24)
        rows.append({"library_id": lib, "source_path": f"C:/synthetic/{i}.jpg", "rel_path": f"{i}.jpg",
                     "status": "ok", "content_hash": _h(i), "width": 4000, "height": 3000,
                     "capture_time": f"{2020 + month // 12}-{month % 12 + 1:02d}-10T10:00:00",
                     "is_blurry": 0, "is_screenshot": 0, "exposure_issue": None, **kw})
        return i

    for _ in range(n_kept):
        photo()
    for _ in range(n_blurry):
        photo(is_blurry=1)
    for _ in range(n_screens):
        photo(is_screenshot=1)
    for _ in range(n_dark):
        photo(exposure_issue="underexposed")
    group_members = [[photo(), photo()] for _ in range(n_groups)]
    with repo.db.connect() as c:
        cols = list(rows[0])
        c.executemany(f"INSERT INTO photos({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                      [[r[k] for k in cols] for r in rows])
        for a, b in group_members:
            gid = c.execute("INSERT INTO duplicate_groups(library_id, kind, best_photo_id, size) VALUES(?, 'near', ?, 2)",
                            (lib, a)).lastrowid
            c.execute("UPDATE photos SET duplicate_group_id = ?, is_group_best = (id = ?) WHERE id IN (?, ?)",
                      (gid, a, a, b))
    return lib


def _core(sample):
    return [(it["content_hash"], it["stratum"]) for it in sample["items"]]


def test_allocate_proportional_with_minimum():
    a = _allocate({"x": 100, "y": 10, "z": 3}, 30, 5)
    assert sum(a.values()) == 30 and a["z"] == 3 and a["y"] >= 5 and a["x"] > a["y"]
    assert _allocate({"x": 2, "y": 1}, 50, 10) == {"x": 2, "y": 1}  # fewer than asked: take all
    assert _allocate({}, 10, 1) == {}


def test_sample_strata_and_determinism(repo):
    lib = _synthetic_library(repo)
    s1, s2 = build_sample(repo, lib, seed=7), build_sample(repo, lib, seed=7)
    assert _core(s1) == _core(s2)  # deterministic
    assert _core(build_sample(repo, lib, seed=8)) != _core(s1)
    c = s1["counts"]
    assert c["random_kept"] == 150 and c["filtered"] == 70 and c["dup_groups"] == 15 and c["dup_group_photos"] == 30
    assert c["filtered_by_reason"]["low_quality"] >= 10 and c["filtered_by_reason"]["screenshot"] >= 10
    assert c["filtered_by_reason"]["exposure"] == 5  # fewer than the minimum exist: take them all
    assert c["filtered_by_reason"]["duplicate"] >= 10
    # every capture month of the kept photos is represented
    kept_months = {repo.get_photo(it["photo_id"])["capture_time"][:7] for it in s1["items"] if it["stratum"] == "random_kept"}
    assert len(kept_months) == 24
    hashes = [it["content_hash"] for it in s1["items"]]
    assert len(hashes) == len(set(hashes))  # no photo twice
    # dup groups are whole and grouped at the end
    dup = [it for it in s1["items"] if it["stratum"] == "dup_groups"]
    assert all(sum(d["group_id"] == g for d in dup) == 2 for g in {d["group_id"] for d in dup})
    assert s1["items"][-len(dup):] == dup
    assert s1["shortfall"] == {}


def test_held_out_rate_and_flag():
    hashes = [_h(i) for i in range(5000)]
    rate = sum(map(is_held_out, hashes)) / len(hashes)
    assert 0.27 < rate < 0.33
    assert is_held_out("00000000" + "f" * 56) and not is_held_out("00000009" + "0" * 56)


def test_small_library_never_fails(repo):
    lib = _synthetic_library(repo, n_kept=12, n_blurry=2, n_screens=0, n_dark=0, n_groups=1)
    s = build_sample(repo, lib)
    assert s["counts"]["random_kept"] == 12 and s["counts"]["filtered"] == 2  # the dup group went to dup_groups
    assert set(s["shortfall"]) == {"random_kept", "filtered", "dup_groups"}
    empty = repo.create_library("C:/empty", "empty")["id"]
    assert build_sample(repo, empty)["items"] == []


def test_nominate_adds_once(repo):
    lib = _synthetic_library(repo, n_kept=5, n_blurry=0, n_screens=0, n_dark=0, n_groups=0)
    s = build_sample(repo, lib)
    photo = {"id": 999, "content_hash": _h(999)}
    assert nominate(s, photo) and not nominate(s, photo)
    assert s["items"][-1]["stratum"] == "nominated"
    assert not nominate(s, {"id": 1, "content_hash": s["items"][0]["content_hash"]})  # already sampled


def test_cli_reads_db_read_only(repo, settings, tmp_path, monkeypatch):
    import evaluation.make_seed_sample as cli

    lib = _synthetic_library(repo, n_kept=30, n_blurry=3, n_screens=0, n_dark=0, n_groups=2)
    monkeypatch.setenv("APP_DATA_DIR", str(settings.data_dir))
    before = settings.db_path.read_bytes()
    out = tmp_path / "s.json"
    assert cli.main(["--library", str(lib), "--db", str(settings.db_path), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["counts"]["random_kept"] == 30
    assert cli.main(["--library", str(lib), "--db", str(settings.db_path), "--out", str(out)]) == 1  # no overwrite
    assert cli.main(["--library", "999", "--db", str(settings.db_path), "--out", str(tmp_path / "x.json")]) == 2
    assert settings.db_path.read_bytes() == before
    # really read-only: a write through the CLI's connection fails
    with pytest.raises(sqlite3.OperationalError):
        with cli.ReadOnlyDatabase(settings.db_path).connect() as c:
            c.execute("DELETE FROM photos")


def test_sample_path_is_outside_repo(settings):
    p = seed_sample.sample_path(settings.data_dir, 3)
    assert p.parent == settings.data_dir / "seed" and p.name == "seed_sample_lib3.json"
