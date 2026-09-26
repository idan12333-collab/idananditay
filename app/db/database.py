"""SQLite storage (MVP). All SQL lives in app.db; business logic uses the repository.

Short-lived connections (one per unit of work) + WAL mode keep this safe to use from
the API threads and the background ingestion thread at the same time.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 4  # v3 is reserved for ADR-016 (separate change)
# v4 (2026-09-26): drop photos.is_low_res, quality_score without resolution, review_labels (ADR-017/018)

# Tables whose IDs appear in URLs, labels or projects. AUTOINCREMENT guarantees a deleted ID is
# never handed out again (plain INTEGER PRIMARY KEY reuses max(id)+1 after deletes).
NEVER_REUSED_ID_TABLES = ("libraries", "duplicate_groups", "photos")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS libraries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    root_path    TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    last_scan_at TEXT
);

CREATE TABLE IF NOT EXISTS photos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id          INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    source_path         TEXT NOT NULL,
    rel_path            TEXT NOT NULL,
    file_size           INTEGER,
    file_mtime          REAL,
    status              TEXT NOT NULL,          -- ok | error | missing
    error               TEXT,
    content_hash        TEXT,                   -- sha256 of file bytes
    phash               TEXT,                   -- 64-bit perceptual hash (hex)
    dhash               TEXT,                   -- 64-bit difference hash (hex)
    format              TEXT,
    mime_type           TEXT,
    width               INTEGER,                -- after EXIF orientation
    height              INTEGER,
    orientation         INTEGER,
    capture_time        TEXT,                   -- ISO-8601, naive local time
    capture_time_source TEXT,                   -- exif | filename | file_mtime
    tz_offset           TEXT,
    camera_make         TEXT,
    camera_model        TEXT,
    gps_lat             REAL,
    gps_lon             REAL,
    gps_alt             REAL,
    sharpness           REAL,
    brightness          REAL,
    contrast            REAL,
    dark_fraction       REAL,
    bright_fraction     REAL,
    exposure_issue      TEXT,                   -- underexposed | overexposed | NULL
    quality_score       REAL,                   -- 0..1 technical quality
    is_blurry           INTEGER NOT NULL DEFAULT 0,
    is_screenshot       INTEGER NOT NULL DEFAULT 0,
    screenshot_reason   TEXT,
    thumbnail_path      TEXT,                   -- relative to thumbnails dir
    duplicate_group_id  INTEGER REFERENCES duplicate_groups(id) ON DELETE SET NULL,
    is_group_best       INTEGER NOT NULL DEFAULT 0,
    embedding_status    TEXT NOT NULL DEFAULT 'pending',
    face_status         TEXT NOT NULL DEFAULT 'pending',
    indexed_at          TEXT,
    UNIQUE (library_id, source_path)
);

CREATE INDEX IF NOT EXISTS ix_photos_library_status ON photos(library_id, status);
CREATE INDEX IF NOT EXISTS ix_photos_capture_time ON photos(library_id, capture_time);
CREATE INDEX IF NOT EXISTS ix_photos_content_hash ON photos(content_hash);
CREATE INDEX IF NOT EXISTS ix_photos_dup_group ON photos(duplicate_group_id);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id    INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,                -- exact | near
    best_photo_id INTEGER,                      -- effective keeper (the user's pick wins, ADR-018)
    auto_best_photo_id INTEGER,                 -- what the automatic rule chose
    size          INTEGER NOT NULL
);

-- Human review labels (ADR-018). Kept apart from the automatic analysis in `photos`, which a label
-- never modifies. Keyed by file content so a label survives rescans and follows identical copies.
CREATE TABLE IF NOT EXISTS review_labels (
    content_hash  TEXT PRIMARY KEY,
    verdict       TEXT NOT NULL CHECK (verdict IN ('good', 'bad')),
    reasons       TEXT NOT NULL DEFAULT '[]',   -- JSON array of reason tags
    note          TEXT,
    photo_id      INTEGER,                      -- photo it was labeled from (informational)
    auto_snapshot TEXT,                         -- JSON: automatic flags/metrics shown at label time
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- The user's choice of which photo to keep in a duplicate group (ADR-018). Keyed by content so it
-- survives the regrouping every scan performs; nothing is ever deleted.
CREATE TABLE IF NOT EXISTS duplicate_picks (
    content_hash  TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    library_id  INTEGER REFERENCES libraries(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    status      TEXT NOT NULL,                  -- queued | running | done | failed | cancelled | interrupted
    phase       TEXT,
    total       INTEGER NOT NULL DEFAULT 0,
    processed   INTEGER NOT NULL DEFAULT 0,
    skipped     INTEGER NOT NULL DEFAULT 0,
    errors      INTEGER NOT NULL DEFAULT 0,
    message     TEXT,
    stats_json  TEXT,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> list[int]:
        """Create/upgrade the schema. Returns the schema versions migrated to (empty if none)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        applied: list[int] = []
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            version = _stored_version(conn)
            if version == 1:
                _migrate_v1_to_v2(conn)
                applied.append(2)
            conn.executescript(SCHEMA)
            if version is not None and version < 4:
                _migrate_to_v4(conn)
                applied.append(4)
            _ensure_additive_columns(conn)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )
        return applied

    def ping(self) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1").fetchone()[0] == 1


def _stored_version(conn: sqlite3.Connection) -> int | None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone() is None:
        return None
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return int(row[0]) if row else None


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """v1 -> v2: rebuild ID tables with AUTOINCREMENT so deleted IDs are never reused.

    SQLite cannot add AUTOINCREMENT in place, so each table is copied into a new definition
    (the documented create-copy-drop-rename procedure). Existing IDs are preserved.
    """
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")  # only takes effect outside a transaction
    try:
        script = ["BEGIN;"]
        for table in NEVER_REUSED_ID_TABLES:
            ddl = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \(.*?\n\);", SCHEMA, re.S).group(0)
            # Copy only columns the current definition still has (v1 photos had is_low_res).
            cols = ", ".join(c for c in _table_columns(conn, table) if c in _ddl_columns(ddl))
            script += [
                ddl.replace(f"CREATE TABLE IF NOT EXISTS {table} (", f"CREATE TABLE {table}__v2 ("),
                f"INSERT INTO {table}__v2 ({cols}) SELECT {cols} FROM {table};",
            ]
        script += [f"DROP TABLE {t};" for t in NEVER_REUSED_ID_TABLES]
        script += [f"ALTER TABLE {t}__v2 RENAME TO {t};" for t in NEVER_REUSED_ID_TABLES]
        script += ["UPDATE meta SET value = '2' WHERE key = 'schema_version';", "COMMIT;"]
        conn.executescript("\n".join(script))
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise RuntimeError(f"schema migration v1->v2 left {len(problems)} broken references")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _ddl_columns(ddl: str) -> set[str]:
    body = ddl.split("(", 1)[1]
    return {m.group(1) for m in re.finditer(r"^\s+([a-z_]+)\s+[A-Z]", body, re.M)}


def _ensure_additive_columns(conn: sqlite3.Connection) -> None:
    """Columns added to v4 after some databases were already upgraded to v4 (idempotent)."""
    if "auto_best_photo_id" not in _table_columns(conn, "duplicate_groups"):
        conn.execute("ALTER TABLE duplicate_groups ADD COLUMN auto_best_photo_id INTEGER")


def _migrate_to_v4(conn: sqlite3.Connection) -> None:
    """-> v4 (ADR-017/018): resolution is no longer a technical-quality signal.

    - drop ``photos.is_low_res`` (the old 1-megapixel flag; print suitability is now derived from
      width/height per print size, see app.printing.suitability),
    - recompute ``quality_score`` from the stored measurements without the resolution component,
    - ``review_labels`` is created by SCHEMA.
    Duplicate-group "best" photos are refreshed by the app afterwards (app.ingest.pipeline).
    """
    from app.vision.quality.classical import combined_quality_score  # only needed for this one-off

    if "is_low_res" in _table_columns(conn, "photos"):
        conn.execute("ALTER TABLE photos DROP COLUMN is_low_res")
    rows = conn.execute(
        "SELECT id, sharpness, exposure_issue, contrast FROM photos WHERE sharpness IS NOT NULL AND contrast IS NOT NULL"
    ).fetchall()
    conn.executemany(
        "UPDATE photos SET quality_score = ? WHERE id = ?",
        [(combined_quality_score(r["sharpness"], r["exposure_issue"], r["contrast"]), r["id"]) for r in rows],
    )
