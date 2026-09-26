"""Ingestion pipeline: scan -> analyze (parallel) -> persist -> duplicate grouping.

Incremental: files whose size and mtime are unchanged since the last scan are skipped.
Files that disappeared are marked ``missing`` (never deleted automatically).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger, log_event
from app.db.repository import Repository
from app.ingest.analyzer import AnalyzeConfig, analyze_file
from app.ingest.duplicates import find_duplicate_groups
from app.ingest.scanner import ScannedFile, exclusion_key, scan_folder

logger = get_logger("ingest.pipeline")

BATCH_SIZE = 50
PROGRESS_INTERVAL_S = 0.5
# How often the analysis loop wakes up while waiting for results, so cancel is honoured promptly and
# progress stays live even when one file is slow (e.g. OneDrive downloading it).
POLL_S = 0.5
# After this long without any finished file, the job reports that it is waiting for a slow file.
SLOW_NOTICE_S = 10.0
# Worker processes take a few seconds to start (imports); timeouts are not counted before then.
POOL_STARTUP_GRACE_S = 30.0

ProgressCallback = Callable[..., None]


class IngestCancelled(Exception):
    pass


@dataclass
class IngestSummary:
    library_id: int
    files_found: int = 0
    analyzed: int = 0
    skipped_unchanged: int = 0
    errors: int = 0
    missing: int = 0
    excluded: int = 0  # files skipped because the user excluded them (ADR-016)
    cloud_only: int = 0  # OneDrive online-only files: not read (reading = download/hang); rescan once local
    duplicate_groups: int = 0
    redundant_duplicates: int = 0
    elapsed_s: float = 0.0
    analyze_s: float = 0.0
    seconds_per_1000: float | None = None
    workers: int = 1
    error_samples: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _is_unchanged(f: ScannedFile, prev: dict | None) -> bool:
    return (
        prev is not None
        and prev["status"] == "ok"
        and prev["file_size"] == f.size
        and prev["file_mtime"] is not None
        and abs(prev["file_mtime"] - f.mtime) < 1e-3
    )


class IngestionPipeline:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    def analyze_config(self) -> AnalyzeConfig:
        s = self.settings
        return AnalyzeConfig(
            thumbnails_dir=str(s.thumbnails_dir),
            thumbnail_size=s.thumbnail_size,
            thumbnail_quality=s.thumbnail_quality,
            analysis_max_side=s.analysis_max_side,
            blur_threshold=s.blur_threshold,
        )

    def _analyze_all(self, paths: list[str], workers: int) -> Iterator[dict | None]:
        """Analysis records in *completion* order, plus ``None`` heartbeats every POLL_S.

        Heartbeats let the caller check cancel and report progress while a file is slow; results are
        not held back behind a slow file (the old in-order ``pool.map`` froze progress AND cancel).
        A file that takes longer than ``analyze_file_timeout_s`` yields an error record and is
        abandoned; the scan continues and a rescan retries it.
        """
        config = self.analyze_config()
        timeout = self.settings.analyze_file_timeout_s or None
        if workers <= 1 or len(paths) < 8:
            yield from _analyze_in_thread(paths, config, timeout)
            return
        pool = ProcessPoolExecutor(max_workers=workers)
        pending = iter(paths)
        inflight: dict[Future, str] = {}
        started: dict[Future, float] = {}
        hung = False
        pool_started = time.monotonic()
        workers_up = False  # set by the first finished file: from then on the pool is really running

        def fill() -> None:
            # At most one file per worker: nothing waits in the pool's queue behind a stuck worker,
            # so "running" really means running and the per-file clock is fair.
            for p in pending:
                inflight[pool.submit(analyze_file, p, config)] = p
                if len(inflight) >= workers:
                    break

        try:
            fill()
            while inflight:
                done, _ = wait(inflight, timeout=POLL_S, return_when=FIRST_COMPLETED)
                workers_up = workers_up or bool(done)
                for fut in done:
                    path = inflight.pop(fut)
                    started.pop(fut, None)
                    try:
                        yield fut.result()
                    except Exception as exc:  # a crashed worker must not stop the scan
                        yield _error_record(path, f"{type(exc).__name__}: {exc}")
                now = time.monotonic()
                clock_on = workers_up or now - pool_started > POOL_STARTUP_GRACE_S
                for fut in list(inflight):
                    if fut.running() and clock_on:
                        started.setdefault(fut, now)
                    if timeout and now - started.get(fut, now) > timeout:
                        path = inflight.pop(fut)
                        started.pop(fut, None)
                        hung = True
                        yield _timeout_record(path, timeout)
                fill()
                if not done:
                    yield None
        finally:
            # On cancel/error/timeout, drop queued work; never wait on a worker that is stuck in a read
            # (that wait would never return, which is what made "cancel" a no-op).
            stuck = hung or bool(inflight)
            procs = _worker_processes(pool) if stuck else []  # shutdown() forgets them, so take them first
            pool.shutdown(wait=not stuck, cancel_futures=True)
            _terminate(procs)

    def run(
        self,
        library_id: int,
        progress: ProgressCallback | None = None,
        cancel: threading.Event | None = None,
    ) -> IngestSummary:
        library = self.repo.get_library(library_id)
        if library is None:
            raise ValueError(f"library {library_id} not found")
        root = Path(library["root_path"])
        self.settings.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        progress = progress or (lambda **_: None)
        t0 = time.perf_counter()
        summary = IngestSummary(library_id=library_id)

        progress(phase="scanning")
        # User exclusions (ADR-016) are matched by relative path before the scanner touches a file,
        # so excluded files are never stat-ed, read, analyzed, thumbnailed or deduplicated.
        excluded_keys = self.repo.get_exclusion_keys(library_id)
        skipped: list[Path] = []
        files = scan_folder(root, excluded_keys, skipped)
        summary.files_found = len(files)
        summary.excluded = len(skipped)
        previous = self.repo.get_file_index(library_id)
        # OneDrive "online-only" files are never opened: reading one makes Windows download it, which
        # can take minutes or hang (real incident 2026-09-26). An earlier index record, if any, is
        # kept as is; the owner is told how to make them local, and the next scan picks them up.
        cloud = [f for f in files if f.cloud_only and not _is_unchanged(f, previous.get(str(f.path)))]
        summary.cloud_only = len(cloud)
        cloud_paths = {str(f.path) for f in cloud}
        todo = [f for f in files if str(f.path) not in cloud_paths and not _is_unchanged(f, previous.get(str(f.path)))]
        summary.skipped_unchanged = len(files) - len(todo) - len(cloud)
        seen = {str(f.path) for f in files}

        def _is_excluded(source_path: str) -> bool:
            try:
                return exclusion_key(Path(source_path).relative_to(root).as_posix()) in excluded_keys
            except ValueError:
                return False

        gone = [p for p in previous if p not in seen]
        # Indexed earlier, excluded now: 'excluded' (not 'missing'); its thumbnail is released.
        _, orphaned = self.repo.mark_excluded(
            library_id, [p for p in gone if previous[p]["status"] != "excluded" and _is_excluded(p)]
        )
        for rel in orphaned:
            (self.settings.thumbnails_dir / rel).unlink(missing_ok=True)
        summary.missing = self.repo.mark_missing(
            library_id, [p for p in gone if previous[p]["status"] != "missing" and not _is_excluded(p)]
        )
        log_event(logger, "scan complete", library_id=library_id, found=len(files), to_analyze=len(todo),
                  cloud_only=len(cloud))

        workers = self.settings.effective_workers()
        summary.workers = workers
        done = summary.skipped_unchanged + summary.cloud_only
        progress(phase="analyzing", total=len(files), processed=done, skipped=summary.skipped_unchanged, errors=0)

        batch: list[dict] = []
        last_report = 0.0
        ta = time.perf_counter()
        last_result = time.perf_counter()
        waiting = False
        for rec in self._analyze_all([str(f.path) for f in todo], workers):
            if cancel is not None and cancel.is_set():
                self.repo.upsert_photos(library_id, batch)
                raise IngestCancelled()
            if rec is None:  # heartbeat: nothing finished in the last POLL_S
                if not waiting and time.perf_counter() - last_result > SLOW_NOTICE_S:
                    waiting = True
                    progress(phase="waiting_file", processed=done, errors=summary.errors)
                continue
            last_result = time.perf_counter()
            if waiting:
                waiting = False
                progress(phase="analyzing")
            rec["rel_path"] = Path(rec["source_path"]).relative_to(root).as_posix()
            if rec["status"] == "error":
                summary.errors += 1
                if len(summary.error_samples) < 20:
                    summary.error_samples.append({"path": rec["rel_path"], "error": rec["error"]})
                log_event(logger, "file failed", level=30, path=rec["rel_path"], error=rec["error"])
            summary.analyzed += 1
            done += 1
            batch.append(rec)
            if len(batch) >= BATCH_SIZE:
                self.repo.upsert_photos(library_id, batch)
                batch = []
            now = time.perf_counter()
            if now - last_report >= PROGRESS_INTERVAL_S:
                progress(processed=done, errors=summary.errors)
                last_report = now
        self.repo.upsert_photos(library_id, batch)
        summary.analyze_s = round(time.perf_counter() - ta, 3)
        progress(phase="deduplicating", processed=done, errors=summary.errors)

        groups = self.update_duplicates(library_id)
        summary.duplicate_groups = len(groups)
        summary.redundant_duplicates = sum(len(g.member_ids) - 1 for g in groups)

        self.repo.touch_library_scan(library_id)
        summary.elapsed_s = round(time.perf_counter() - t0, 3)
        if summary.analyzed:
            summary.seconds_per_1000 = round(summary.analyze_s / summary.analyzed * 1000, 1)
        log_event(logger, "ingest finished", **{k: v for k, v in summary.to_dict().items() if k != "error_samples"})
        return summary

    def update_duplicates(self, library_id: int):
        candidates = self.repo.get_dedup_candidates(library_id)
        groups = find_duplicate_groups(
            candidates,
            phash_threshold=self.settings.near_dup_phash_threshold,
            dhash_threshold=self.settings.near_dup_dhash_threshold,
            picks=self.repo.get_duplicate_picks(),
            burst_window_s=self.settings.near_dup_burst_window_s,
            burst_phash_threshold=self.settings.near_dup_burst_phash_threshold,
        )
        self.repo.replace_duplicate_groups(library_id, groups)
        return groups


def refresh_duplicate_groups(settings: Settings, repo: Repository) -> int:
    """Recompute duplicate groups (and their best photo) of every library from stored hashes.

    Used after a schema migration that changes quality scores or the best-photo rule (v4, ADR-017);
    cheap — no image is decoded. Returns the number of libraries refreshed.
    """
    pipeline = IngestionPipeline(settings, repo)
    libraries = repo.list_libraries()
    for lib in libraries:
        pipeline.update_duplicates(lib["id"])
    return len(libraries)


def _error_record(path: str, error: str) -> dict:
    return {"source_path": path, "status": "error", "error": error}


def _timeout_record(path: str, timeout: float) -> dict:
    log_event(logger, "file timed out", level=30, path=path, timeout_s=timeout)
    return _error_record(
        path, f"Timed out after {timeout:g} s (the file may be downloading from OneDrive); a rescan retries it"
    )


def _analyze_in_thread(paths: list[str], config: AnalyzeConfig, timeout: float | None) -> Iterator[dict | None]:
    """Small scans / one worker: analyze in a daemon thread so a stuck read can be abandoned.

    A thread blocked in the OS cannot be killed; it is left behind as a daemon (it never keeps the
    app from exiting) and the scan moves on.
    """
    for path in paths:
        box: dict = {}

        def work(p: str = path) -> None:
            try:
                box["rec"] = analyze_file(p, config)
            except Exception as exc:
                box["rec"] = _error_record(p, f"{type(exc).__name__}: {exc}")

        t = threading.Thread(target=work, name="analyze-file", daemon=True)
        t0 = time.monotonic()
        t.start()
        while True:
            t.join(POLL_S)
            if not t.is_alive():
                yield box["rec"]
                break
            if timeout and time.monotonic() - t0 > timeout:
                yield _timeout_record(path, timeout)
                break
            yield None


def _worker_processes(pool: ProcessPoolExecutor) -> list:
    """The pool's worker processes. No public API; ``_processes`` is stable across 3.8-3.13 and is
    cleared by ``shutdown()``, so it must be read before."""
    return list((getattr(pool, "_processes", None) or {}).values())


def _terminate(procs: list) -> None:
    """Kill worker processes that are still running (e.g. blocked reading a cloud-only file);
    left alive they would also keep the app from exiting."""
    for proc in procs:
        try:
            if proc.is_alive():
                proc.terminate()
        except Exception:  # best effort: the scan result is already safe in the database
            pass
