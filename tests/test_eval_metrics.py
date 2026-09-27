"""Curation evaluation metrics (evaluation/metrics.py): read-only, correct joins and rates."""

from __future__ import annotations

import sqlite3

import pytest

from app.db.database import Database
from evaluation import metrics as m

NOW = "2026-09-27T10:00:00"
PARAMS = {"long_px": 600, "short_px": 400}


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "eval.sqlite3"
    Database(path).initialize()
    c = sqlite3.connect(path)
    c.execute("INSERT INTO libraries(id, root_path, name, created_at) VALUES (1, 'X:/lib', 'lib', ?)", (NOW,))
    c.execute("INSERT INTO duplicate_groups(id, library_id, kind, best_photo_id, auto_best_photo_id, size) VALUES (7, 1, 'near', 5, 4, 2)")

    def photo(pid, h, *, blurry=0, shot=0, exposure=None, group=None, best=0, w=4000, hgt=3000):
        c.execute(
            "INSERT INTO photos(id, library_id, source_path, rel_path, status, content_hash, width, height, "
            "is_blurry, is_screenshot, exposure_issue, duplicate_group_id, is_group_best) "
            "VALUES (?, 1, ?, ?, 'ok', ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, f"X:/lib/{pid}.jpg", f"{pid}.jpg", h, w, hgt, blurry, shot, exposure, group, best),
        )

    def label(h, worth, special=0, held=0, stratum="random_kept"):
        c.execute(
            "INSERT INTO curation_labels(content_hash, worthiness, special, held_out, stratum, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", (h, worth, special, held, stratum, NOW, NOW))

    photo(1, "h1")                      # kept, must
    photo(2, "h2", blurry=1)            # low_quality, must + special -> moment_missed
    photo(3, "h3", shot=1)              # screenshot, no -> correct exclusion
    photo(4, "h4", group=7, best=0)     # duplicate alternate (auto keeper was 4, owner picked 5)
    photo(5, "h5", group=7, best=1)
    photo(6, "h6")                      # kept, no -> junk_retained
    photo(8, "h1")                      # identical copy of photo 1 -> counted once
    label("h1", "must")
    label("h2", "must", special=1, held=1, stratum="filtered")
    label("h3", "no", stratum="filtered")
    label("h4", "maybe", stratum="filtered")
    label("h6", "no")
    label("orphan", "maybe")
    c.execute("INSERT INTO jobs(id, library_id, kind, status, total, created_at, started_at, finished_at) "
              "VALUES ('j', 1, 'ingest', 'done', 500, '2026-09-27T10:00:00', '2026-09-27T10:00:00', '2026-09-27T10:00:30')")
    c.commit()
    c.close()
    return path


def _rows(db_path):
    conn = m.connect_ro(db_path)
    try:
        return m.load_labeled(conn, 1, PARAMS), conn.execute("SELECT 1").fetchone()
    finally:
        conn.close()


def test_wilson_interval():
    assert m.wilson(0, 0) is None
    lo, hi = m.wilson(0, 68)
    assert lo == 0 and 0.04 < hi < 0.06
    lo, hi = m.wilson(5, 10)
    assert lo < 0.5 < hi


def test_load_joins_labels_once_per_content(db_path):
    (rows, orphans), _ = _rows(db_path)
    assert sorted(r["id"] for r in rows) == [1, 2, 3, 4, 6]
    assert orphans == 1
    reasons = {r["id"]: r["auto_reason"] for r in rows}
    assert reasons == {1: None, 2: "low_quality", 3: "screenshot", 4: "duplicate", 6: None}


def test_metrics_values(db_path):
    (rows, _), _ = _rows(db_path)
    got = m.compute(rows, "auto")
    assert (got.m1_false_exclusion_must.k, got.m1_false_exclusion_must.n) == (1, 2)
    assert (got.m2_special_lost.k, got.m2_special_lost.n) == (1, 1)
    # The duplicate alternate reaches ranking through its keeper: recall = 2 of 3 wanted.
    assert (got.m3_candidate_recall.k, got.m3_candidate_recall.n) == (2, 3)
    assert (got.m4_junk_retention.k, got.m4_junk_retention.n) == (1, 2)
    assert got.by_reason["screenshot"]["no"] == 1


def test_duplicates_runtime_and_failures(db_path):
    conn = m.connect_ro(db_path)
    try:
        (rows, _) = m.load_labeled(conn, 1, PARAMS)
        dup = m.duplicate_agreement(conn, 1, rows)
        assert m.runtime_per_1000(conn, 1) == pytest.approx(60.0)
    finally:
        conn.close()
    assert dup["owner_changed"] == [7] and dup["groups"] == 1
    kinds = {(f["kind"], f["photo_id"]) for f in m.failures(rows, dup)}
    assert kinds == {("moment_missed", 2), ("junk_retained", 6)}


def test_connection_is_read_only(db_path):
    conn = m.connect_ro(db_path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM curation_labels")
    finally:
        conn.close()


def test_main_writes_report_without_file_names(db_path, tmp_path):
    out = tmp_path / "reports"
    assert m.main(["--library", "1", "--db", str(db_path), "--out", str(out), "--date", "2026-09-27"]) == 0
    report = (out / "round0_2026-09-27.md").read_text(encoding="utf-8")
    assert "M2 special moments lost" in report and ".jpg" not in report
    assert "2.jpg" in (out / "local" / "round0_2026-09-27_failures.csv").read_text(encoding="utf-8-sig")
