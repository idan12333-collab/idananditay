"""Data access for libraries, photos, duplicate groups and jobs."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from app.db.database import Database

# Columns written by ingestion (everything except id/library_id/duplicate fields).
PHOTO_INGEST_FIELDS: tuple[str, ...] = (
    "source_path", "rel_path", "file_size", "file_mtime", "status", "error",
    "content_hash", "phash", "dhash", "format", "mime_type", "width", "height", "orientation",
    "capture_time", "capture_time_source", "tz_offset", "camera_make", "camera_model",
    "gps_lat", "gps_lon", "gps_alt",
    "sharpness", "brightness", "contrast", "dark_fraction", "bright_fraction", "exposure_issue",
    "quality_score", "is_blurry", "is_low_res", "is_screenshot", "screenshot_reason",
    "thumbnail_path", "indexed_at",
)

# Values used when an ingest record lacks a field (e.g. files that failed to decode).
_FIELD_DEFAULTS: dict[str, Any] = {"is_blurry": 0, "is_low_res": 0, "is_screenshot": 0}

# Named filters for the gallery. Keys are part of the public API.
PHOTO_FILTERS: dict[str, str] = {
    "all": "status = 'ok'",
    "unique": "status = 'ok' AND (duplicate_group_id IS NULL OR is_group_best = 1)",
    "duplicates": "status = 'ok' AND duplicate_group_id IS NOT NULL AND is_group_best = 0",
    "blurry": "status = 'ok' AND is_blurry = 1",
    "low_res": "status = 'ok' AND is_low_res = 1",
    "screenshots": "status = 'ok' AND is_screenshot = 1",
    "exposure": "status = 'ok' AND exposure_issue IS NOT NULL",
    "no_date": "status = 'ok' AND (capture_time IS NULL OR capture_time_source = 'file_mtime')",
    "gps": "status = 'ok' AND gps_lat IS NOT NULL",
    "errors": "status = 'error'",
    "missing": "status = 'missing'",
}

PHOTO_SORTS: dict[str, str] = {
    "date": "capture_time IS NULL, capture_time, id",
    "date_desc": "capture_time IS NULL, capture_time DESC, id",
    "quality": "quality_score IS NULL, quality_score DESC, id",
    "path": "rel_path, id",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row(r) -> dict[str, Any] | None:
    return dict(r) if r is not None else None


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ---------------------------------------------------------------- libraries
    def create_library(self, root_path: str, name: str) -> dict:
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO libraries(root_path, name, created_at) VALUES(?, ?, ?) "
                "ON CONFLICT(root_path) DO NOTHING",
                (root_path, name, now_iso()),
            )
            return _row(c.execute("SELECT * FROM libraries WHERE root_path = ?", (root_path,)).fetchone())

    def get_library(self, library_id: int) -> dict | None:
        with self.db.connect() as c:
            return _row(c.execute("SELECT * FROM libraries WHERE id = ?", (library_id,)).fetchone())

    def list_libraries(self) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT l.*, (SELECT COUNT(*) FROM photos p WHERE p.library_id = l.id AND p.status = 'ok') "
                "AS photo_count FROM libraries l ORDER BY l.id"
            ).fetchall()
            return [dict(r) for r in rows]

    def touch_library_scan(self, library_id: int) -> None:
        with self.db.connect() as c:
            c.execute("UPDATE libraries SET last_scan_at = ? WHERE id = ?", (now_iso(), library_id))

    def delete_library(self, library_id: int) -> list[str]:
        """Delete a library and all its derived data. Returns thumbnail paths no longer referenced."""
        with self.db.connect() as c:
            thumbs = {
                r[0]
                for r in c.execute(
                    "SELECT DISTINCT thumbnail_path FROM photos WHERE library_id = ? AND thumbnail_path IS NOT NULL",
                    (library_id,),
                )
            }
            c.execute("DELETE FROM photos WHERE library_id = ?", (library_id,))
            c.execute("DELETE FROM duplicate_groups WHERE library_id = ?", (library_id,))
            c.execute("DELETE FROM jobs WHERE library_id = ?", (library_id,))
            c.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
            still_used = {
                r[0]
                for r in c.execute("SELECT DISTINCT thumbnail_path FROM photos WHERE thumbnail_path IS NOT NULL")
            }
        return sorted(thumbs - still_used)

    # ------------------------------------------------------------------- photos
    def get_file_index(self, library_id: int) -> dict[str, dict]:
        """source_path -> {size, mtime, status} for incremental rescans."""
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT source_path, file_size, file_mtime, status FROM photos WHERE library_id = ?",
                (library_id,),
            ).fetchall()
        return {r["source_path"]: dict(r) for r in rows}

    def upsert_photos(self, library_id: int, records: Sequence[dict]) -> None:
        if not records:
            return
        cols = ", ".join(PHOTO_INGEST_FIELDS)
        placeholders = ", ".join("?" for _ in PHOTO_INGEST_FIELDS)
        updates = ", ".join(f"{f} = excluded.{f}" for f in PHOTO_INGEST_FIELDS if f != "source_path")
        sql = (
            f"INSERT INTO photos(library_id, {cols}) VALUES(?, {placeholders}) "
            f"ON CONFLICT(library_id, source_path) DO UPDATE SET {updates}"
        )
        with self.db.connect() as c:
            c.executemany(
                sql,
                [
                    (library_id, *(rec[f] if rec.get(f) is not None else _FIELD_DEFAULTS.get(f)
                                   for f in PHOTO_INGEST_FIELDS))
                    for rec in records
                ],
            )

    def mark_missing(self, library_id: int, source_paths: Iterable[str]) -> int:
        paths = list(source_paths)
        if not paths:
            return 0
        with self.db.connect() as c:
            c.executemany(
                "UPDATE photos SET status = 'missing', duplicate_group_id = NULL, is_group_best = 0 "
                "WHERE library_id = ? AND source_path = ?",
                [(library_id, p) for p in paths],
            )
        return len(paths)

    def get_photo(self, photo_id: int) -> dict | None:
        with self.db.connect() as c:
            return _row(c.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone())

    def list_photos(
        self,
        library_id: int,
        filter_name: str = "all",
        year: int | None = None,
        sort: str = "date",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        if filter_name not in PHOTO_FILTERS:
            raise ValueError(f"unknown filter: {filter_name}")
        if sort not in PHOTO_SORTS:
            raise ValueError(f"unknown sort: {sort}")
        where = f"library_id = ? AND {PHOTO_FILTERS[filter_name]}"
        params: list[Any] = [library_id]
        if year is not None:
            where += " AND substr(capture_time, 1, 4) = ?"
            params.append(f"{year:04d}")
        with self.db.connect() as c:
            total = c.execute(f"SELECT COUNT(*) FROM photos WHERE {where}", params).fetchone()[0]
            rows = c.execute(
                f"SELECT * FROM photos WHERE {where} ORDER BY {PHOTO_SORTS[sort]} LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [dict(r) for r in rows], total

    def get_dedup_candidates(self, library_id: int) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT id, content_hash, phash, dhash, quality_score, width, height FROM photos "
                "WHERE library_id = ? AND status = 'ok' AND phash IS NOT NULL ORDER BY id",
                (library_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def replace_duplicate_groups(self, library_id: int, groups: Sequence) -> None:
        """Atomically replace all duplicate groups of a library. ``groups`` are DuplicateGroup objects."""
        with self.db.connect() as c:
            c.execute(
                "UPDATE photos SET duplicate_group_id = NULL, is_group_best = 0 WHERE library_id = ?",
                (library_id,),
            )
            c.execute("DELETE FROM duplicate_groups WHERE library_id = ?", (library_id,))
            for g in groups:
                cur = c.execute(
                    "INSERT INTO duplicate_groups(library_id, kind, best_photo_id, size) VALUES(?, ?, ?, ?)",
                    (library_id, g.kind, g.best_id, len(g.member_ids)),
                )
                gid = cur.lastrowid
                c.executemany(
                    "UPDATE photos SET duplicate_group_id = ?, is_group_best = ? WHERE id = ?",
                    [(gid, int(pid == g.best_id), pid) for pid in g.member_ids],
                )

    def list_duplicate_groups(self, library_id: int, offset: int = 0, limit: int = 50) -> tuple[list[dict], int]:
        with self.db.connect() as c:
            total = c.execute(
                "SELECT COUNT(*) FROM duplicate_groups WHERE library_id = ?", (library_id,)
            ).fetchone()[0]
            groups = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM duplicate_groups WHERE library_id = ? ORDER BY size DESC, id LIMIT ? OFFSET ?",
                    (library_id, limit, offset),
                )
            ]
            for g in groups:
                g["members"] = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM photos WHERE duplicate_group_id = ? ORDER BY is_group_best DESC, id",
                        (g["id"],),
                    )
                ]
        return groups, total

    def get_group_members(self, group_id: int) -> list[dict]:
        with self.db.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM photos WHERE duplicate_group_id = ? ORDER BY is_group_best DESC, id", (group_id,)
                )
            ]

    def library_stats(self, library_id: int) -> dict:
        with self.db.connect() as c:
            s = dict(
                c.execute(
                    """
                    SELECT
                      COUNT(*)                                                     AS total_files,
                      COALESCE(SUM(status = 'ok'), 0)                              AS indexed,
                      COALESCE(SUM(status = 'error'), 0)                           AS errors,
                      COALESCE(SUM(status = 'missing'), 0)                         AS missing,
                      COALESCE(SUM(status = 'ok' AND is_blurry = 1), 0)            AS blurry,
                      COALESCE(SUM(status = 'ok' AND is_low_res = 1), 0)           AS low_res,
                      COALESCE(SUM(status = 'ok' AND is_screenshot = 1), 0)        AS screenshots,
                      COALESCE(SUM(status = 'ok' AND exposure_issue IS NOT NULL), 0) AS exposure_issues,
                      COALESCE(SUM(status = 'ok' AND gps_lat IS NOT NULL), 0)      AS with_gps,
                      COALESCE(SUM(status = 'ok' AND capture_time_source = 'exif'), 0)     AS date_from_exif,
                      COALESCE(SUM(status = 'ok' AND capture_time_source = 'filename'), 0) AS date_from_filename,
                      COALESCE(SUM(status = 'ok' AND capture_time_source = 'file_mtime'), 0) AS date_from_file_mtime,
                      COALESCE(SUM(status = 'ok' AND duplicate_group_id IS NOT NULL AND is_group_best = 0), 0)
                                                                                   AS redundant_duplicates,
                      COALESCE(SUM(status = 'ok' AND (duplicate_group_id IS NULL OR is_group_best = 1)), 0)
                                                                                   AS unique_photos,
                      MIN(CASE WHEN status = 'ok' THEN capture_time END)           AS earliest,
                      MAX(CASE WHEN status = 'ok' THEN capture_time END)           AS latest
                    FROM photos WHERE library_id = ?
                    """,
                    (library_id,),
                ).fetchone()
            )
            s["duplicate_groups"] = {
                r["kind"]: r["n"]
                for r in c.execute(
                    "SELECT kind, COUNT(*) AS n FROM duplicate_groups WHERE library_id = ? GROUP BY kind",
                    (library_id,),
                )
            }
            s["years"] = [
                {"year": r["y"], "count": r["n"]}
                for r in c.execute(
                    "SELECT substr(capture_time, 1, 4) AS y, COUNT(*) AS n FROM photos "
                    "WHERE library_id = ? AND status = 'ok' AND capture_time IS NOT NULL GROUP BY y ORDER BY y",
                    (library_id,),
                )
            ]
        s["duplicate_reduction_pct"] = (
            round(100.0 * s["redundant_duplicates"] / s["indexed"], 1) if s["indexed"] else 0.0
        )
        return s

    # --------------------------------------------------------------------- jobs
    def create_job(self, job_id: str, library_id: int, kind: str) -> dict:
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO jobs(id, library_id, kind, status, created_at) VALUES(?, ?, ?, 'queued', ?)",
                (job_id, library_id, kind, now_iso()),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def update_job(self, job_id: str, **fields) -> None:
        if not fields:
            return
        if "stats" in fields:
            fields["stats_json"] = json.dumps(fields.pop("stats"), ensure_ascii=False)
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.db.connect() as c:
            c.execute(f"UPDATE jobs SET {sets} WHERE id = ?", (*fields.values(), job_id))

    def get_job(self, job_id: str) -> dict | None:
        with self.db.connect() as c:
            job = _row(c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
        return _decode_job(job)

    def latest_job(self, library_id: int) -> dict | None:
        with self.db.connect() as c:
            job = _row(
                c.execute(
                    "SELECT * FROM jobs WHERE library_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                    (library_id,),
                ).fetchone()
            )
        return _decode_job(job)

    def active_job(self, library_id: int) -> dict | None:
        with self.db.connect() as c:
            job = _row(
                c.execute(
                    "SELECT * FROM jobs WHERE library_id = ? AND status IN ('queued', 'running') LIMIT 1",
                    (library_id,),
                ).fetchone()
            )
        return _decode_job(job)

    def interrupt_stale_jobs(self) -> int:
        with self.db.connect() as c:
            cur = c.execute(
                "UPDATE jobs SET status = 'interrupted', finished_at = ?, message = 'App stopped during job' "
                "WHERE status IN ('queued', 'running')",
                (now_iso(),),
            )
            return cur.rowcount


def _decode_job(job: dict | None) -> dict | None:
    if job is None:
        return None
    raw = job.pop("stats_json", None)
    job["stats"] = json.loads(raw) if raw else None
    return job
