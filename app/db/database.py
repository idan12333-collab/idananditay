"""SQLite storage (MVP). All SQL lives in app.db; business logic uses the repository.

Short-lived connections (one per unit of work) + WAL mode keep this safe to use from
the API threads and the background ingestion thread at the same time.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS libraries (
    id           INTEGER PRIMARY KEY,
    root_path    TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    last_scan_at TEXT
);

CREATE TABLE IF NOT EXISTS photos (
    id                  INTEGER PRIMARY KEY,
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
    is_low_res          INTEGER NOT NULL DEFAULT 0,
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
    id            INTEGER PRIMARY KEY,
    library_id    INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,                -- exact | near
    best_photo_id INTEGER,
    size          INTEGER NOT NULL
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

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def ping(self) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1").fetchone()[0] == 1
