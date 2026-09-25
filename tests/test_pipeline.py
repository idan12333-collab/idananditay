import os
import time

from app.ingest.pipeline import IngestionPipeline
from app.ingest.scanner import scan_folder
from tests.conftest import fingerprint


def _by_name(repo, library_id):
    rows, _ = repo.list_photos(library_id, "all", limit=500)
    errors, _ = repo.list_photos(library_id, "errors", limit=500)
    return {os.path.basename(r["source_path"]): r for r in rows + errors}


def test_scanner_recursive_filters(library):
    root, _ = library
    names = sorted(f.path.name for f in scan_folder(root))
    assert "a_copy.jpg" in names  # nested Hebrew folder
    assert "notes.txt" not in names
    assert "ignored.jpg" not in names  # hidden folder
    assert len(names) == 11


def test_full_ingest(settings, repo, library):
    root, paths = library
    before = fingerprint(root)
    lib = repo.create_library(str(root.resolve()), "test")
    summary = IngestionPipeline(settings, repo).run(lib["id"])

    assert summary.files_found == 11
    assert summary.errors == 1
    assert summary.analyzed == 11
    assert fingerprint(root) == before, "originals must never be modified"

    rows = _by_name(repo, lib["id"])
    a = rows["a.jpg"]
    assert a["capture_time"] == "2019-05-12T10:00:00" and a["capture_time_source"] == "exif"
    assert a["gps_lat"] is not None and a["camera_make"] == "TestCam"
    assert (a["width"], a["height"]) == (1400, 1000)
    assert (settings.thumbnails_dir / a["thumbnail_path"]).is_file()

    assert rows["rotated.jpg"]["width"] == 900 and rows["rotated.jpg"]["height"] == 1200
    assert rows["IMG_20210304_101112.jpg"]["capture_time_source"] == "filename"
    assert rows["blurry.jpg"]["is_blurry"] == 1
    assert rows["a.jpg"]["is_blurry"] == 0
    assert rows["tiny.jpg"]["is_low_res"] == 1
    assert rows["Screenshot_2023-01-01.png"]["is_screenshot"] == 1
    assert rows["dark.jpg"]["exposure_issue"] == "underexposed"
    assert rows["corrupt.jpg"]["status"] == "error"

    # a, a_copy (exact) and a_small (near) form one group; best = full-size original.
    group_id = a["duplicate_group_id"]
    assert group_id is not None
    members = {os.path.basename(m["source_path"]) for m in repo.get_group_members(group_id)}
    assert members == {"a.jpg", "a_copy.jpg", "a_small.jpg"}
    best = [m for m in repo.get_group_members(group_id) if m["is_group_best"]]
    assert len(best) == 1 and os.path.basename(best[0]["source_path"]) in {"a.jpg", "a_copy.jpg"}
    assert rows["b.png"]["duplicate_group_id"] is None

    stats = repo.library_stats(lib["id"])
    assert stats["indexed"] == 10 and stats["errors"] == 1
    assert stats["redundant_duplicates"] == 2 and stats["unique_photos"] == 8
    assert {y["year"] for y in stats["years"]} >= {"2019", "2020", "2021", "2022"}


def test_incremental_rescan(settings, repo, library):
    root, paths = library
    lib = repo.create_library(str(root.resolve()), "test")
    pipe = IngestionPipeline(settings, repo)
    pipe.run(lib["id"])

    second = pipe.run(lib["id"])
    assert second.skipped_unchanged == 10  # all OK files skipped
    assert second.analyzed == 1            # the corrupt file is retried

    # Modify one file, delete another -> only the changed file is re-analyzed.
    os.remove(paths["b"])
    new_time = time.time() + 5
    paths["tiny"].write_bytes(paths["a_small"].read_bytes())
    os.utime(paths["tiny"], (new_time, new_time))
    third = pipe.run(lib["id"])
    assert third.missing == 1
    assert third.analyzed == 2  # tiny (changed) + corrupt (retry)
    rows = _by_name(repo, lib["id"])
    assert (rows["tiny.jpg"]["width"], rows["tiny.jpg"]["height"]) == (840, 600)  # re-analyzed
    missing, _ = repo.list_photos(lib["id"], "missing")
    assert [os.path.basename(m["source_path"]) for m in missing] == ["b.png"]
    # tiny.jpg is now an exact copy of a_small -> joins the "a" group.
    assert rows["tiny.jpg"]["duplicate_group_id"] == rows["a.jpg"]["duplicate_group_id"]


def test_parallel_workers_match_sequential(settings, repo, library):
    root, _ = library
    settings.ingest_workers = 2
    lib = repo.create_library(str(root.resolve()), "test")
    summary = IngestionPipeline(settings, repo).run(lib["id"])
    assert summary.workers == 2 and summary.analyzed == 11 and summary.errors == 1
    assert repo.library_stats(lib["id"])["redundant_duplicates"] == 2
