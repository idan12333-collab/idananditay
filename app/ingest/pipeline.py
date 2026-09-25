"""Ingestion pipeline: scan -> analyze (parallel) -> persist -> duplicate grouping.

Incremental: files whose size and mtime are unchanged since the last scan are skipped.
Files that disappeared are marked ``missing`` (never deleted automatically).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger, log_event
from app.db.repository import Repository
from app.ingest.analyzer import AnalyzeConfig, analyze_file
from app.ingest.duplicates import find_duplicate_groups
from app.ingest.scanner import ScannedFile, scan_folder

logger = get_logger("ingest.pipeline")

BATCH_SIZE = 50
PROGRESS_INTERVAL_S = 0.5

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
            low_res_min_megapixels=s.low_res_min_megapixels,
        )

    def _analyze_all(self, paths: list[str], workers: int) -> Iterator[dict]:
        config = self.analyze_config()
        if workers <= 1 or len(paths) < 8:
            for p in paths:
                yield analyze_file(p, config)
            return
        pool = ProcessPoolExecutor(max_workers=workers)
        try:
            yield from pool.map(analyze_file, paths, [config] * len(paths), chunksize=4)
        finally:
            # On cancel/error, drop queued work instead of finishing the whole library.
            pool.shutdown(wait=True, cancel_futures=True)

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
        files = scan_folder(root)
        summary.files_found = len(files)
        previous = self.repo.get_file_index(library_id)
        todo = [f for f in files if not _is_unchanged(f, previous.get(str(f.path)))]
        summary.skipped_unchanged = len(files) - len(todo)
        seen = {str(f.path) for f in files}
        summary.missing = self.repo.mark_missing(
            library_id, [p for p, row in previous.items() if p not in seen and row["status"] != "missing"]
        )
        log_event(logger, "scan complete", library_id=library_id, found=len(files), to_analyze=len(todo))

        workers = self.settings.effective_workers()
        summary.workers = workers
        done = summary.skipped_unchanged
        progress(phase="analyzing", total=len(files), processed=done, skipped=summary.skipped_unchanged, errors=0)

        batch: list[dict] = []
        last_report = 0.0
        ta = time.perf_counter()
        for rec in self._analyze_all([str(f.path) for f in todo], workers):
            if cancel is not None and cancel.is_set():
                self.repo.upsert_photos(library_id, batch)
                raise IngestCancelled()
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
        )
        self.repo.replace_duplicate_groups(library_id, groups)
        return groups
