"""Data access for libraries, photos, duplicate groups and jobs."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from app.db.database import Database
from app.printing.suitability import PrintPolicy

# Columns written by ingestion (everything except id/library_id/duplicate fields).
PHOTO_INGEST_FIELDS: tuple[str, ...] = (
    "source_path", "rel_path", "file_size", "file_mtime", "status", "error",
    "content_hash", "phash", "dhash", "format", "mime_type", "width", "height", "orientation",
    "capture_time", "capture_time_source", "tz_offset", "camera_make", "camera_model",
    "gps_lat", "gps_lon", "gps_alt",
    "sharpness", "brightness", "contrast", "dark_fraction", "bright_fraction", "exposure_issue",
    "quality_score", "is_blurry", "is_screenshot", "screenshot_reason",
    "thumbnail_path", "indexed_at",
)

# Values used when an ingest record lacks a field (e.g. files that failed to decode).
_FIELD_DEFAULTS: dict[str, Any] = {"is_blurry": 0, "is_screenshot": 0}

# The automatic filter's reasons (classical rules, not AI), as SQL over `photos`. A photo with any of
# them is "filtered" by the automatic analysis — never deleted or hidden: it stays one click away and
# a human label overrides the decision (ADR-018). {long_px}/{short_px} come from the PrintPolicy
# (ADR-017): "extremely low resolution" = cannot fill the smallest slot at acceptable PPI.
AUTO_FLAGS: dict[str, str] = {
    "blurry": "is_blurry = 1",
    "exposure": "exposure_issue IS NOT NULL",
    "screenshot": "is_screenshot = 1",
    "extreme_low_res": "(MAX(width, height) < {long_px} OR MIN(width, height) < {short_px})",
    "duplicate": "(duplicate_group_id IS NOT NULL AND is_group_best = 0)",
}
_ANY_AUTO_FLAG = "(" + " OR ".join(AUTO_FLAGS.values()) + ")"
_LABEL = "(SELECT r.verdict FROM review_labels r WHERE r.content_hash = photos.content_hash)"
# The filter's effective decision (ADR-018). Two independent parts:
# 1. Duplicates: in each group exactly one copy stays (automatic choice or the user's pick); a human
#    label never changes that — another copy is kept only by picking it in the duplicates view.
# 2. Technical reasons (screenshot, quality, exposure): a "good" label overrides all of them,
#    "bad" removes the photo even without a reason. COALESCE keeps unlabeled photos out of NULL logic.
_DUP_ALT = AUTO_FLAGS["duplicate"]
_ANY_TECH = "(" + " OR ".join(v for k, v in AUTO_FLAGS.items() if k != "duplicate") + ")"
_LV = f"COALESCE({_LABEL}, '')"
_FILTERED = f"({_DUP_ALT} OR {_LV} = 'bad' OR ({_LV} <> 'good' AND {_ANY_TECH}))"
# Each filtered photo is shown under ONE primary reason; NULL for kept photos.
PRIMARY_REASONS = ("duplicate", "screenshot", "low_quality", "exposure", "manual")
_PRIMARY = (
    f"(CASE WHEN {_DUP_ALT} THEN 'duplicate' WHEN {_LV} = 'good' THEN NULL "
    f"WHEN {AUTO_FLAGS['screenshot']} THEN 'screenshot' "
    f"WHEN ({AUTO_FLAGS['blurry']} OR {AUTO_FLAGS['extreme_low_res']}) THEN 'low_quality' "
    f"WHEN {AUTO_FLAGS['exposure']} THEN 'exposure' WHEN {_LV} = 'bad' THEN 'manual' END)"
)

# Named filters for the gallery. Keys are part of the public API.
PHOTO_FILTERS: dict[str, str] = {
    "all": "status = 'ok'",
    "unique": "status = 'ok' AND (duplicate_group_id IS NULL OR is_group_best = 1)",
    "duplicates": "status = 'ok' AND duplicate_group_id IS NOT NULL AND is_group_best = 0",
    "blurry": "status = 'ok' AND is_blurry = 1",
    "extreme_low_res": f"status = 'ok' AND {AUTO_FLAGS['extreme_low_res']}",
    "screenshots": "status = 'ok' AND is_screenshot = 1",
    "exposure": "status = 'ok' AND exposure_issue IS NOT NULL",
    "no_date": "status = 'ok' AND (capture_time IS NULL OR capture_time_source = 'file_mtime')",
    "gps": "status = 'ok' AND gps_lat IS NOT NULL",
    "errors": "status = 'error'",
    "missing": "status = 'missing'",
    # Human review (ADR-018)
    "unreviewed": f"status = 'ok' AND {_LABEL} IS NULL",
    "review_good": f"status = 'ok' AND {_LABEL} = 'good'",
    "review_bad": f"status = 'ok' AND {_LABEL} = 'bad'",
    # Automatic analysis and human disagree: flagged but labeled good, or unflagged but labeled bad.
    "review_disagree": f"status = 'ok' AND (({_ANY_AUTO_FLAG} AND {_LABEL} = 'good') "
                       f"OR (NOT {_ANY_AUTO_FLAG} AND {_LABEL} = 'bad'))",
    # The filter's effective decision: the human label wins; otherwise the automatic reasons decide.
    # COALESCE: an unlabeled photo must compare as '' (not NULL), or NOT(...) would drop it from both lists.
    "filtered": f"status = 'ok' AND {_FILTERED}",
    "kept": f"status = 'ok' AND NOT {_FILTERED}",
    "auto_filtered": f"status = 'ok' AND {_ANY_AUTO_FLAG}",
    "auto_kept": f"status = 'ok' AND NOT {_ANY_AUTO_FLAG}",
    # Photos whose outcome the user changed (restored despite a technical reason, or removed without one).
    "changes": f"status = 'ok' AND (({_LV} = 'good' AND {_ANY_TECH} AND NOT {_DUP_ALT}) "
               f"OR ({_LV} = 'bad' AND NOT ({_DUP_ALT} OR {_ANY_TECH})))",
    **{f"reason_{r}": f"status = 'ok' AND {_PRIMARY} = '{r}'" for r in PRIMARY_REASONS},
}

REVIEW_VERDICTS = ("good", "bad")
# Optional reason tags a reviewer can attach. Tags that correspond to an automatic flag are used to
# measure that flag's agreement with the human reviewer.
REVIEW_REASONS = ("blurry", "exposure", "low_res", "screenshot", "duplicate", "not_a_photo", "other")
FLAG_REASON = {"blurry": "blurry", "exposure": "exposure", "screenshot": "screenshot", "extreme_low_res": "low_res",
               "duplicate": "duplicate"}

CURATION_WORTHINESS = ("must", "maybe", "no")  # ADR-022: keys 1/2/3 in quick labeling

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
    def __init__(self, db: Database, print_policy: PrintPolicy | None = None):
        self.db = db
        self.print_policy = print_policy or PrintPolicy()
        long_px, short_px = self.print_policy.extreme_low_res_pixels()
        self._sql_params = {"long_px": long_px, "short_px": short_px}

    def _sql(self, template: str) -> str:
        """Fill policy numbers (ints computed by us, never user input) into a filter template."""
        return template.format(**self._sql_params)

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
            c.execute("DELETE FROM library_exclusions WHERE library_id = ?", (library_id,))
            c.execute("DELETE FROM libraries WHERE id = ?", (library_id,))
            # Review labels are personal derived data too: drop those no remaining photo refers to.
            c.execute(
                "DELETE FROM review_labels WHERE content_hash NOT IN "
                "(SELECT content_hash FROM photos WHERE content_hash IS NOT NULL)"
            )
            c.execute(
                "DELETE FROM duplicate_picks WHERE content_hash NOT IN "
                "(SELECT content_hash FROM photos WHERE content_hash IS NOT NULL)"
            )
            still_used = {
                r[0]
                for r in c.execute("SELECT DISTINCT thumbnail_path FROM photos WHERE thumbnail_path IS NOT NULL")
            }
        return sorted(thumbs - still_used)

    # --------------------------------------------------------------- exclusions
    def set_exclusions(self, library_id: int, rel_paths: Iterable[str]) -> int:
        """Replace the library's exclusion list (paths relative to the root, '/'-separated)."""
        from app.ingest.scanner import exclusion_key

        rows = {exclusion_key(p): p for p in rel_paths}
        with self.db.connect() as c:
            c.execute("DELETE FROM library_exclusions WHERE library_id = ?", (library_id,))
            c.executemany(
                "INSERT INTO library_exclusions(library_id, rel_key, rel_path, created_at) VALUES(?, ?, ?, ?)",
                [(library_id, k, p, now_iso()) for k, p in rows.items()],
            )
        return len(rows)

    def get_exclusions(self, library_id: int) -> list[str]:
        with self.db.connect() as c:
            return [
                r[0]
                for r in c.execute(
                    "SELECT rel_path FROM library_exclusions WHERE library_id = ? ORDER BY rel_path", (library_id,)
                )
            ]

    def get_exclusion_keys(self, library_id: int) -> frozenset[str]:
        with self.db.connect() as c:
            return frozenset(
                r[0] for r in c.execute("SELECT rel_key FROM library_exclusions WHERE library_id = ?", (library_id,))
            )

    def mark_excluded(self, library_id: int, source_paths: Iterable[str]) -> tuple[int, list[str]]:
        """Previously indexed files the user has now excluded: status 'excluded' (not 'missing').

        Their thumbnails are released; returns (count, thumbnail paths no longer referenced by any photo).
        """
        paths = list(source_paths)
        if not paths:
            return 0, []
        with self.db.connect() as c:
            thumbs = set()
            for p in paths:
                r = c.execute(
                    "SELECT thumbnail_path FROM photos WHERE library_id = ? AND source_path = ?", (library_id, p)
                ).fetchone()
                if r and r[0]:
                    thumbs.add(r[0])
            c.executemany(
                "UPDATE photos SET status = 'excluded', duplicate_group_id = NULL, is_group_best = 0, "
                "thumbnail_path = NULL WHERE library_id = ? AND source_path = ?",
                [(library_id, p) for p in paths],
            )
            still_used = {
                r[0]
                for r in c.execute("SELECT DISTINCT thumbnail_path FROM photos WHERE thumbnail_path IS NOT NULL")
            }
        return len(paths), sorted(thumbs - still_used)

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
        where = f"library_id = ? AND {self._sql(PHOTO_FILTERS[filter_name])}"
        params: list[Any] = [library_id]
        if year is not None:
            where += " AND substr(capture_time, 1, 4) = ?"
            params.append(f"{year:04d}")
        with self.db.connect() as c:
            total = c.execute(f"SELECT COUNT(*) FROM photos WHERE {where}", params).fetchone()[0]
            rows = c.execute(
                f"SELECT *, {_LABEL} AS review_verdict FROM photos WHERE {where} "
                f"ORDER BY {PHOTO_SORTS[sort]} LIMIT ? OFFSET ?",
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
                    "INSERT INTO duplicate_groups(library_id, kind, best_photo_id, auto_best_photo_id, size) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (library_id, g.kind, g.best_id, g.auto_best_id or g.best_id, len(g.member_ids)),
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
                        f"SELECT *, {_LABEL} AS review_verdict FROM photos WHERE duplicate_group_id = ? ORDER BY is_group_best DESC, id",
                        (g["id"],),
                    )
                ]
        return groups, total

    def get_duplicate_group(self, group_id: int) -> dict | None:
        with self.db.connect() as c:
            g = _row(c.execute("SELECT * FROM duplicate_groups WHERE id = ?", (group_id,)).fetchone())
        if g:
            g["members"] = self.get_group_members(group_id)
        return g

    def get_group_members(self, group_id: int) -> list[dict]:
        with self.db.connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    f"SELECT *, {_LABEL} AS review_verdict FROM photos WHERE duplicate_group_id = ? ORDER BY is_group_best DESC, id", (group_id,)
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
                      COALESCE(SUM(status = 'excluded'), 0)                        AS excluded_indexed,
                      COALESCE(SUM(status = 'ok' AND is_blurry = 1), 0)            AS blurry,
                      COALESCE(SUM(status = 'ok' AND {extreme_low_res}), 0)        AS extreme_low_res,
                      COALESCE(SUM(status = 'ok' AND {label} IS NOT NULL), 0)      AS reviewed,
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
                    """.format(extreme_low_res=self._sql(AUTO_FLAGS["extreme_low_res"]), label=_LABEL),
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
        s["exclusions"] = len(self.get_exclusions(library_id))
        s["duplicate_reduction_pct"] = (
            round(100.0 * s["redundant_duplicates"] / s["indexed"], 1) if s["indexed"] else 0.0
        )
        return s

    # ------------------------------------------------------------ human review
    # Labels live in `review_labels` (ADR-018) and never modify the automatic analysis in `photos`.
    def get_review(self, content_hash: str | None) -> dict | None:
        if not content_hash:
            return None
        with self.db.connect() as c:
            return _decode_review(
                _row(c.execute("SELECT * FROM review_labels WHERE content_hash = ?", (content_hash,)).fetchone())
            )

    def set_review(
        self,
        photo: dict,
        verdict: str,
        reasons: Sequence[str] = (),
        note: str | None = None,
        auto_snapshot: dict | None = None,
    ) -> dict:
        if verdict not in REVIEW_VERDICTS:
            raise ValueError(f"verdict must be one of {REVIEW_VERDICTS}")
        unknown = set(reasons) - set(REVIEW_REASONS)
        if unknown:
            raise ValueError(f"unknown reasons: {sorted(unknown)}")
        if not photo.get("content_hash"):
            raise ValueError("photo has no content hash (not analyzed)")
        now = now_iso()
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO review_labels(content_hash, verdict, reasons, note, photo_id, auto_snapshot, "
                "created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(content_hash) DO UPDATE SET verdict = excluded.verdict, reasons = excluded.reasons, "
                "note = excluded.note, photo_id = excluded.photo_id, auto_snapshot = excluded.auto_snapshot, "
                "updated_at = excluded.updated_at",
                (
                    photo["content_hash"], verdict, json.dumps(sorted(set(reasons))), (note or "").strip() or None,
                    photo["id"], json.dumps(auto_snapshot or {}, ensure_ascii=False), now, now,
                ),
            )
        return self.get_review(photo["content_hash"])  # type: ignore[return-value]

    def delete_review(self, content_hash: str | None) -> bool:
        if not content_hash:
            return False
        with self.db.connect() as c:
            return c.execute("DELETE FROM review_labels WHERE content_hash = ?", (content_hash,)).rowcount > 0

    def review_stats(self, library_id: int) -> dict:
        """How well each automatic flag agrees with the human reviewer, on reviewed photos only.

        Per flag: of the reviewed photos the flag marked, how many the human called bad
        (``flagged_bad``, i.e. the flag was right) or good (``flagged_good``, a false alarm); and
        how many unflagged reviewed photos the human called bad for that same reason (``missed``).
        Each photo counts once even if identical copies exist.
        """
        base = (
            "SELECT p.*, r.verdict, r.reasons FROM photos p JOIN review_labels r ON r.content_hash = p.content_hash "
            "WHERE p.library_id = ? AND p.status = 'ok' "
            "AND p.id = (SELECT MIN(q.id) FROM photos q WHERE q.library_id = p.library_id "
            "AND q.status = 'ok' AND q.content_hash = p.content_hash)"
        )
        flag_cols = ", ".join(f"{self._sql(sql)} AS f_{k}" for k, sql in AUTO_FLAGS.items())
        with self.db.connect() as c:
            rows = [dict(r) for r in c.execute(f"SELECT b.verdict, b.reasons, {flag_cols} FROM ({base}) b", (library_id,))]
            unreviewed = c.execute(
                self._sql(f"SELECT COUNT(*) FROM photos WHERE library_id = ? AND {PHOTO_FILTERS['unreviewed']}"),
                (library_id,),
            ).fetchone()[0]
        out: dict[str, Any] = {
            "reviewed": len(rows),
            "unreviewed": unreviewed,
            "good": sum(r["verdict"] == "good" for r in rows),
            "bad": sum(r["verdict"] == "bad" for r in rows),
            "flags": {},
        }
        for flag, reason in FLAG_REASON.items():
            flagged = [r for r in rows if r[f"f_{flag}"]]
            unflagged = [r for r in rows if not r[f"f_{flag}"]]
            fb = sum(r["verdict"] == "bad" for r in flagged)
            out["flags"][flag] = {
                "flagged_reviewed": len(flagged),
                "flagged_bad": fb,
                "flagged_good": len(flagged) - fb,
                "flag_precision": round(fb / len(flagged), 3) if flagged else None,
                "missed": sum(r["verdict"] == "bad" and reason in json.loads(r["reasons"]) for r in unflagged),
            }
        any_flag = [any(r[f"f_{k}"] for k in AUTO_FLAGS) for r in rows]
        out["agree"] = sum(f == (r["verdict"] == "bad") for f, r in zip(any_flag, rows))
        out["disagree"] = len(rows) - out["agree"]
        return out

    def filter_summary(self, library_id: int) -> dict:
        """What the automatic filter did, per reason, and how the human feedback changed it (ADR-018)."""
        count = lambda c, name: c.execute(  # noqa: E731
            f"SELECT COUNT(*) FROM photos WHERE library_id = ? AND {self._sql(PHOTO_FILTERS[name])}", (library_id,)
        ).fetchone()[0]
        with self.db.connect() as c:
            # One primary reason per filtered photo, so the tabs add up to `filtered`.
            by_reason = {r: count(c, f"reason_{r}") for r in PRIMARY_REASONS}
            out = {name: count(c, name) for name in ("all", "auto_filtered", "auto_kept", "filtered", "kept")}
            restored = c.execute(
                f"SELECT COUNT(*) FROM photos WHERE library_id = ? AND status = 'ok' "
                f"AND {self._sql(_ANY_TECH)} AND NOT {_DUP_ALT} AND {_LV} = 'good'", (library_id,)).fetchone()[0]
            should_filter = c.execute(
                f"SELECT COUNT(*) FROM photos WHERE library_id = ? AND status = 'ok' "
                f"AND NOT ({_DUP_ALT} OR {self._sql(_ANY_TECH)}) AND {_LV} = 'bad'", (library_id,)).fetchone()[0]
            changed_picks = c.execute(
                "SELECT COUNT(*) FROM duplicate_groups WHERE library_id = ? AND auto_best_photo_id IS NOT NULL "
                "AND best_photo_id != auto_best_photo_id", (library_id,)).fetchone()[0]
            groups = c.execute("SELECT COUNT(*) FROM duplicate_groups WHERE library_id = ?", (library_id,)).fetchone()[0]
        return {
            "total": out["all"],
            "auto_filtered": out["auto_filtered"],
            "auto_kept": out["auto_kept"],
            "filtered": out["filtered"],
            "kept": out["kept"],
            "by_reason": by_reason,
            "duplicate_groups": groups,
            "feedback": {"restored": restored, "should_filter": should_filter, "duplicate_picks_changed": changed_picks},
        }

    # --------------------------------------------------------- duplicate picks
    def get_duplicate_picks(self) -> dict[str, str]:
        with self.db.connect() as c:
            return {r[0]: r[1] for r in c.execute("SELECT content_hash, created_at FROM duplicate_picks")}

    def set_duplicate_pick(self, group_id: int, photo: dict) -> None:
        """The user keeps ``photo`` as the group's best; replaces any earlier pick in the same group."""
        members = self.get_group_members(group_id)
        with self.db.connect() as c:
            c.executemany("DELETE FROM duplicate_picks WHERE content_hash = ?",
                          [(m["content_hash"],) for m in members if m.get("content_hash")])
            c.execute("INSERT INTO duplicate_picks(content_hash, created_at) VALUES(?, ?)",
                      (photo["content_hash"], datetime.now().isoformat(timespec="microseconds")))

    def clear_duplicate_picks(self, group_id: int) -> None:
        members = self.get_group_members(group_id)
        with self.db.connect() as c:
            c.executemany("DELETE FROM duplicate_picks WHERE content_hash = ?",
                          [(m["content_hash"],) for m in members if m.get("content_hash")])

    def export_reviews(self, library_id: int) -> list[dict]:
        """Labels of this library joined with the current automatic analysis (evaluation set)."""
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT p.id AS photo_id, p.rel_path, p.content_hash, p.width, p.height, p.sharpness, "
                "p.brightness, p.contrast, p.dark_fraction, p.bright_fraction, p.exposure_issue, p.is_blurry, "
                "p.is_screenshot, p.screenshot_reason, p.quality_score, p.duplicate_group_id, p.is_group_best, "
                "r.verdict, r.reasons, r.note, r.auto_snapshot, r.created_at, r.updated_at "
                "FROM photos p JOIN review_labels r ON r.content_hash = p.content_hash "
                "WHERE p.library_id = ? AND p.status = 'ok' ORDER BY p.rel_path",
                (library_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["reasons"] = json.loads(d["reasons"] or "[]")
            d["auto_snapshot"] = json.loads(d["auto_snapshot"] or "{}")
            d["extreme_low_res"] = self.print_policy.is_extremely_low(d["width"] or 0, d["height"] or 0)
            out.append(d)
        return out

    # ------------------------------------------------------- curation labels
    # The owner's album preference (ADR-022). Stored apart from review_labels and never referenced
    # by PHOTO_FILTERS, so a curation label cannot change filtered/kept or review_stats.
    def get_curation_label(self, content_hash: str | None) -> dict | None:
        if not content_hash:
            return None
        with self.db.connect() as c:
            return _row(c.execute("SELECT * FROM curation_labels WHERE content_hash = ?", (content_hash,)).fetchone())

    def set_curation_label(
        self, photo: dict, worthiness: str, special: bool = False, stratum: str | None = None, held_out: bool = False
    ) -> dict:
        if worthiness not in CURATION_WORTHINESS:
            raise ValueError(f"worthiness must be one of {CURATION_WORTHINESS}")
        if not photo.get("content_hash"):
            raise ValueError("photo has no content hash (not analyzed)")
        now = now_iso()
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO curation_labels(content_hash, worthiness, special, source, blind, held_out, stratum, "
                "rel_path, capture_time, created_at, updated_at) VALUES(?, ?, ?, 'owner', 1, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(content_hash) DO UPDATE SET worthiness = excluded.worthiness, special = excluded.special, "
                "held_out = excluded.held_out, stratum = COALESCE(excluded.stratum, curation_labels.stratum), "
                "rel_path = excluded.rel_path, capture_time = excluded.capture_time, updated_at = excluded.updated_at",
                (photo["content_hash"], worthiness, int(bool(special)), int(bool(held_out)), stratum,
                 photo.get("rel_path"), photo.get("capture_time"), now, now),
            )
        return self.get_curation_label(photo["content_hash"])  # type: ignore[return-value]

    def delete_curation_label(self, content_hash: str | None) -> bool:
        if not content_hash:
            return False
        with self.db.connect() as c:
            return c.execute("DELETE FROM curation_labels WHERE content_hash = ?", (content_hash,)).rowcount > 0

    def delete_all_curation_labels(self) -> int:
        """Privacy: forget every curation label (all libraries)."""
        with self.db.connect() as c:
            return c.execute("DELETE FROM curation_labels").rowcount

    def curation_labels_for(self, content_hashes: Iterable[str]) -> dict[str, dict]:
        hashes = [h for h in content_hashes if h]
        out: dict[str, dict] = {}
        with self.db.connect() as c:
            for i in range(0, len(hashes), 500):
                chunk = hashes[i:i + 500]
                q = f"SELECT * FROM curation_labels WHERE content_hash IN ({','.join('?' * len(chunk))})"
                out.update({r["content_hash"]: dict(r) for r in c.execute(q, chunk)})
        return out

    def find_photo_by_content(self, library_id: int, content_hash: str, photo_id: int | None = None) -> dict | None:
        """An analyzed photo of this library with this content (the given ID first, if it still matches)."""
        with self.db.connect() as c:
            row = c.execute(
                "SELECT * FROM photos WHERE library_id = ? AND content_hash = ? AND status = 'ok' "
                "ORDER BY id = ? DESC, id LIMIT 1", (library_id, content_hash, photo_id or -1),
            ).fetchone()
        return _row(row)

    def seed_progress(self, items: Sequence[dict]) -> dict:
        """Labeling progress over a seed sample's items ({content_hash, stratum}): total, labeled, per stratum."""
        labeled = self.curation_labels_for(it["content_hash"] for it in items)
        strata: dict[str, dict[str, int]] = {}
        for it in items:
            s = strata.setdefault(it["stratum"], {"total": 0, "labeled": 0})
            s["total"] += 1
            s["labeled"] += it["content_hash"] in labeled
        return {"total": len(items), "labeled": sum(s["labeled"] for s in strata.values()), "strata": strata}

    def export_curation_labels(self, library_id: int) -> list[dict]:
        """Curation labels of this library's photos (one row per content) + the filter's decision."""
        with self.db.connect() as c:
            rows = c.execute(
                # `photos` stays unaliased: the shared filter SQL refers to photos.content_hash.
                self._sql(
                    f"SELECT photos.id AS photo_id, photos.rel_path, photos.content_hash, photos.capture_time, "
                    f"l.worthiness, l.special, l.stratum, l.held_out, l.blind, l.source, "
                    f"{_FILTERED} AS filtered, {_PRIMARY} AS filter_reason, "
                    f"photos.is_blurry, photos.is_screenshot, photos.exposure_issue, photos.quality_score, "
                    f"l.created_at, l.updated_at "
                    f"FROM photos JOIN curation_labels l ON l.content_hash = photos.content_hash "
                    f"WHERE photos.library_id = ? AND photos.status = 'ok' "
                    f"AND photos.id = (SELECT MIN(q.id) FROM photos q WHERE q.library_id = photos.library_id "
                    f"AND q.status = 'ok' AND q.content_hash = photos.content_hash) "
                    f"ORDER BY photos.capture_time, photos.rel_path"
                ),
                (library_id,),
            ).fetchall()
        return [dict(r) for r in rows]

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

    def any_active_job(self) -> bool:
        with self.db.connect() as c:
            return c.execute("SELECT 1 FROM jobs WHERE status IN ('queued', 'running') LIMIT 1").fetchone() is not None

    def referenced_thumbnails(self) -> set[str]:
        with self.db.connect() as c:
            return {r[0] for r in c.execute("SELECT DISTINCT thumbnail_path FROM photos WHERE thumbnail_path IS NOT NULL")}

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


def _decode_review(label: dict | None) -> dict | None:
    if label is None:
        return None
    label["reasons"] = json.loads(label.get("reasons") or "[]")
    label["auto_snapshot"] = json.loads(label.get("auto_snapshot") or "{}")
    return label
