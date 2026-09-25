"""Background job runner for long-running work (ingestion).

MVP: a single in-process worker thread; job state is persisted in SQLite so the UI can
poll it. Can be replaced by a real queue later without changing the API contract.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

from app.core.config import Settings
from app.core.logging import get_logger, log_event
from app.db.repository import Repository, now_iso
from app.ingest.pipeline import IngestCancelled, IngestionPipeline

logger = get_logger("services.jobs")


class JobManager:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingest")
        self._cancel: dict[str, threading.Event] = {}
        self._futures: dict[str, Future] = {}
        self._lock = threading.Lock()
        stale = self.repo.interrupt_stale_jobs()
        if stale:
            log_event(logger, "marked stale jobs as interrupted", count=stale)

    def start_scan(self, library_id: int) -> dict:
        with self._lock:
            active = self.repo.active_job(library_id)
            if active:
                return active
            job_id = uuid.uuid4().hex
            job = self.repo.create_job(job_id, library_id, "ingest")
            self._cancel[job_id] = threading.Event()
            self._futures[job_id] = self._executor.submit(self._run_scan, job_id, library_id)
            return job

    def cancel(self, job_id: str) -> bool:
        ev = self._cancel.get(job_id)
        if ev is None:
            return False
        ev.set()
        return True

    def wait(self, job_id: str, timeout: float | None = None) -> dict | None:
        fut = self._futures.get(job_id)
        if fut is not None:
            fut.result(timeout=timeout)
        return self.repo.get_job(job_id)

    def _run_scan(self, job_id: str, library_id: int) -> None:
        self.repo.update_job(job_id, status="running", started_at=now_iso(), phase="starting")

        def progress(**fields) -> None:
            self.repo.update_job(job_id, **fields)

        pipeline = IngestionPipeline(self.settings, self.repo)
        try:
            summary = pipeline.run(library_id, progress=progress, cancel=self._cancel[job_id])
            self.repo.update_job(
                job_id,
                status="done",
                phase="done",
                processed=summary.files_found,
                errors=summary.errors,
                stats=summary.to_dict(),
                finished_at=now_iso(),
            )
        except IngestCancelled:
            self.repo.update_job(job_id, status="cancelled", phase="cancelled", finished_at=now_iso())
        except Exception as exc:
            logger.exception("ingest job failed")
            self.repo.update_job(
                job_id, status="failed", phase="failed", message=f"{type(exc).__name__}: {exc}", finished_at=now_iso()
            )
        finally:
            self._cancel.pop(job_id, None)

    def shutdown(self) -> None:
        for ev in list(self._cancel.values()):
            ev.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
