"""A file that never finishes reading (e.g. OneDrive downloading it) must not freeze a scan or
make "cancel" a no-op. Real incident 2026-09-26: scan stuck at 1,117/1,124, cancel did nothing."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from PIL import Image

import app.ingest.pipeline as pipeline_mod
from app.core.config import Settings
from app.db.database import Database
from app.db.repository import Repository
from app.ingest.analyzer import analyze_file as real_analyze
from app.ingest.pipeline import IngestCancelled, IngestionPipeline

HANG_MARK = "hang_"


def hanging_analyze(path, config):
    """Top-level (picklable) stand-in for analyze_file: files named hang_* block like a stuck read."""
    if Path(path).name.startswith(HANG_MARK):
        time.sleep(600)
    return real_analyze(path, config)


def _library(tmp_path: Path, n: int, hang: int) -> Path:
    root = tmp_path / "photos"
    root.mkdir()
    for i in range(n):
        name = f"{HANG_MARK}{i}.jpg" if i < hang else f"p{i:02d}.jpg"
        Image.new("RGB", (64, 48), (i * 9 % 255, 80, 120)).save(root / name, "JPEG")
    return root


def _setup(tmp_path: Path, workers: int, timeout: float, n: int, hang: int):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", ingest_workers=workers,
                        analyze_file_timeout_s=timeout)
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.initialize()
    repo = Repository(db, settings.print_policy())
    lib = repo.create_library(str(_library(tmp_path, n, hang)), "t")
    return IngestionPipeline(settings, repo), repo, lib["id"]


def _statuses(repo: Repository, lib_id: int) -> dict[str, tuple[str, str | None]]:
    with repo.db.connect() as c:
        return {r[0]: (r[1], r[2]) for r in c.execute(
            "SELECT rel_path, status, error FROM photos WHERE library_id = ?", (lib_id,))}


@pytest.fixture
def hanging(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "analyze_file", hanging_analyze)


@pytest.mark.parametrize("workers,n", [(1, 4), (2, 10)])  # in-thread path and process-pool path
def test_stuck_file_times_out_and_scan_finishes(tmp_path, hanging, workers, n):
    pipeline, repo, lib_id = _setup(tmp_path, workers, timeout=2, n=n, hang=1)
    t0 = time.monotonic()
    summary = pipeline.run(lib_id)
    assert time.monotonic() - t0 < 60
    st = _statuses(repo, lib_id)
    assert st["hang_0.jpg"][0] == "error" and "Timed out" in st["hang_0.jpg"][1]
    assert all(s == "ok" for name, (s, _) in st.items() if name != "hang_0.jpg")
    assert len(st) == n and summary.errors == 1


@pytest.mark.parametrize("workers,n", [(1, 4), (2, 10)])
def test_cancel_works_while_a_file_is_stuck(tmp_path, hanging, workers, n):
    pipeline, repo, lib_id = _setup(tmp_path, workers, timeout=0, n=n, hang=1)  # no timeout at all
    cancel = threading.Event()
    result: dict = {}

    def run():
        try:
            pipeline.run(lib_id, cancel=cancel)
        except IngestCancelled:
            result["cancelled"] = time.monotonic()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(4)  # the stuck file is being "read" now
    asked = time.monotonic()
    cancel.set()
    t.join(20)
    assert "cancelled" in result, "cancel was a no-op while a file hung"
    assert result["cancelled"] - asked < 5


def test_progress_reports_waiting_on_a_slow_file(tmp_path, hanging, monkeypatch):
    monkeypatch.setattr(pipeline_mod, "SLOW_NOTICE_S", 1.0)
    pipeline, _, lib_id = _setup(tmp_path, 1, timeout=3, n=3, hang=1)
    phases: list[str] = []
    pipeline.run(lib_id, progress=lambda **f: phases.append(f.get("phase")) if f.get("phase") else None)
    assert "waiting_file" in phases
    assert phases.index("waiting_file") < len(phases) - 1  # and it went back to normal afterwards


def test_timed_out_file_is_retried_on_rescan(tmp_path, hanging, monkeypatch):
    pipeline, repo, lib_id = _setup(tmp_path, 1, timeout=2, n=3, hang=1)
    pipeline.run(lib_id)
    monkeypatch.setattr(pipeline_mod, "analyze_file", real_analyze)  # "the download finished"
    pipeline.run(lib_id)
    assert _statuses(repo, lib_id)["hang_0.jpg"][0] == "ok"


def test_no_worker_process_left_behind(tmp_path, hanging):
    import multiprocessing

    pipeline, _, lib_id = _setup(tmp_path, 2, timeout=2, n=10, hang=1)
    pipeline.run(lib_id)
    deadline = time.monotonic() + 10
    while multiprocessing.active_children() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert multiprocessing.active_children() == []  # a stuck worker would keep the app from exiting


def test_onedrive_cloud_only_files_are_never_read(tmp_path, monkeypatch):
    """Owner decision 2026-09-27 (option A): online-only files are counted, not read."""
    import app.ingest.scanner as scanner_mod

    cloud_names = {"p01.jpg", "p02.jpg"}
    opened: list[str] = []
    monkeypatch.setattr(scanner_mod, "_is_cloud_only_file", lambda path, st: path.name in cloud_names)
    monkeypatch.setattr(pipeline_mod, "analyze_file", lambda p, c: opened.append(Path(p).name) or real_analyze(p, c))

    pipeline, repo, lib_id = _setup(tmp_path, 1, timeout=30, n=4, hang=0)
    summary = pipeline.run(lib_id)
    assert summary.cloud_only == 2 and not cloud_names & set(opened)
    assert set(_statuses(repo, lib_id)) == {"p00.jpg", "p03.jpg"}  # not indexed, not "missing"

    cloud_names.clear()  # the owner chose "always keep on this device"
    summary = pipeline.run(lib_id)
    assert summary.cloud_only == 0
    assert set(_statuses(repo, lib_id)) == {"p00.jpg", "p01.jpg", "p02.jpg", "p03.jpg"}
