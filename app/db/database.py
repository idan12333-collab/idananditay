"""SQLite storage (MVP). All SQL lives in app.db; business logic uses the repository.

Short-lived connections (one per unit of work) + WAL mode keep this safe to use from
the API threads and the background ingestion thread at the same time.
"""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.logging import get_logger, log_event

logger = get_logger("db")

# Automatic backups taken right before a schema-changing migration (I-004). Kept next to the DB.
MAX_MIGRATION_BACKUPS = 5


class MigrationBackupError(RuntimeError):
    """The pre-migration backup could not be made; the migration was NOT applied."""

SCHEMA_VERSION = 5  # v3 (ADR-016): library_exclusions table — additive, created by SCHEMA on every start
# v4 (2026-09-26): drop photos.is_low_res, quality_score without resolution, review_labels (ADR-017/018)
# v5 (ADR-022): curation_labels + ai_label_proposals — additive, created by SCHEMA (like v3, it has no
#     migration step; the I-004 backup still runs because the stored version is older)

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
    status              TEXT NOT NULL,          -- ok | error | missing | excluded
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

-- Files the user chose not to include in this library (ADR-016). Matched by path relative to the
-- library root; if another file later appears at the same path it is excluded too (by design, MVP).
CREATE TABLE IF NOT EXISTS library_exclusions (
    library_id  INTEGER NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    rel_key     TEXT NOT NULL,                  -- comparison key (see scanner.exclusion_key)
    rel_path    TEXT NOT NULL,                  -- as given, '/'-separated
    created_at  TEXT NOT NULL,
    PRIMARY KEY (library_id, rel_key)
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

-- The owner's album preference per photo (ADR-022): "do I want this in an album?". Separate from
-- review_labels (technical correctness): never read by the filter, so it never changes filtered/kept.
-- Keyed by content; rel_path/capture_time let labels be remapped if the photo is re-imported.
CREATE TABLE IF NOT EXISTS curation_labels (
    content_hash TEXT PRIMARY KEY,
    worthiness   TEXT NOT NULL CHECK (worthiness IN ('must','maybe','no')),
    special      INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'owner',
    blind        INTEGER NOT NULL DEFAULT 1,
    held_out     INTEGER NOT NULL DEFAULT 0,
    stratum      TEXT,
    rel_path     TEXT,
    capture_time TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- AI label suggestions (ADR-022, filled later by I-017). Never read as labels.
CREATE TABLE IF NOT EXISTS ai_label_proposals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL,
    label        TEXT NOT NULL,
    value        TEXT NOT NULL,
    confidence   REAL,
    model_id     TEXT NOT NULL,
    created_at   TEXT NOT NULL
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
        self.last_backup: Path | None = None  # set when initialize() backed up before a migration

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
            version = _stored_version(conn)
        # A migration is about to change an existing database: back it up first, or stop (I-004).
        # Never on a normal start (version already current) or for a brand-new database.
        self.last_backup = (
            backup_before_migration(self.path, version)
            if version is not None and version < SCHEMA_VERSION
            else None
        )
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
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


def backup_before_migration(db_path: Path, from_version: int, keep: int = MAX_MIGRATION_BACKUPS) -> Path:
    """Consistent copy of the database (SQLite online-backup API, WAL-safe) in ``<data>/backups``.

    Raises MigrationBackupError if the copy cannot be made or verified. Older backups beyond ``keep``
    are pruned (a pruning problem is only logged).
    """
    backups = db_path.parent / "backups"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = backups / f"{db_path.stem}-v{from_version}-{stamp}.sqlite3"
    n = 1
    while dest.exists():
        n += 1
        dest = backups / f"{db_path.stem}-v{from_version}-{stamp}-{n}.sqlite3"
    try:
        backups.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(db_path)
        try:
            dst = sqlite3.connect(dest)
            try:
                src.backup(dst)
                ok = dst.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            finally:
                dst.close()
        finally:
            src.close()
        if not ok:
            raise sqlite3.DatabaseError("backup copy failed its integrity check")
    except (OSError, sqlite3.Error) as exc:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        log_event(logger, "migration aborted: backup failed", level=40, db=str(db_path), error=str(exc))
        raise MigrationBackupError(
            f"Could not back up the database before upgrading it (from schema v{from_version}); "
            f"the upgrade was NOT applied. Database: {db_path}. Reason: {exc}"
        ) from exc
    log_event(logger, "database backed up before migration", backup=str(dest), from_version=from_version,
              to_version=SCHEMA_VERSION)
    old = sorted(backups.glob(f"{db_path.stem}-v*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in old[keep:]:
        if p == dest:
            continue
        try:
            p.unlink()
        except OSError as exc:
            log_event(logger, "could not prune old backup", level=30, path=str(p), error=str(exc))
    return dest


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
