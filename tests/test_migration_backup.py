"""I-004: automatic database backup before a schema-changing migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import app.db.database as dbmod
from app.db.database import SCHEMA_VERSION, Database, MigrationBackupError


def _version(path: Path) -> str:
    with sqlite3.connect(path) as c:
        return c.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]


def _old_db(tmp_path: Path) -> Path:
    """A database that reports an older schema version (the v4 migration step is idempotent)."""
    path = tmp_path / "data" / "library.sqlite3"
    Database(path).initialize()
    with sqlite3.connect(path) as c:
        c.execute("UPDATE meta SET value = '3' WHERE key = 'schema_version'")
        c.execute("INSERT INTO libraries(root_path, name, created_at) VALUES('C:/x', 'x', 'now')")
    return path


def _backups(path: Path) -> list[Path]:
    return sorted((path.parent / "backups").glob("*.sqlite3"))


def test_no_backup_on_new_or_current_database(tmp_path):
    path = tmp_path / "data" / "library.sqlite3"
    db = Database(path)
    db.initialize()  # brand new
    db.initialize()  # normal start, already current
    assert db.last_backup is None and _backups(path) == []


def test_backup_made_before_migration(tmp_path):
    path = _old_db(tmp_path)
    db = Database(path)
    db.initialize()
    assert _version(path) == str(SCHEMA_VERSION)
    assert db.last_backup is not None and db.last_backup.parent == path.parent / "backups"
    # The backup is the database as it was *before* the upgrade, with its data.
    assert _version(db.last_backup) == "3"
    with sqlite3.connect(db.last_backup) as c:
        assert c.execute("SELECT name FROM libraries").fetchone()[0] == "x"


def test_failed_backup_blocks_migration(tmp_path, monkeypatch):
    path = _old_db(tmp_path)

    def broken_connect(target, *a, **k):
        if "backups" in str(target):
            raise sqlite3.OperationalError("disk full (simulated)")
        return real_connect(target, *a, **k)

    real_connect = sqlite3.connect
    monkeypatch.setattr(dbmod.sqlite3, "connect", broken_connect)
    with pytest.raises(MigrationBackupError, match="NOT applied"):
        Database(path).initialize()
    monkeypatch.undo()
    assert _version(path) == "3"  # schema version unchanged → migration did not run
    assert _backups(path) == []  # no partial backup left behind


def test_backup_retention(tmp_path):
    path = _old_db(tmp_path)
    for _ in range(dbmod.MAX_MIGRATION_BACKUPS + 3):
        with sqlite3.connect(path) as c:
            c.execute("UPDATE meta SET value = '3' WHERE key = 'schema_version'")
        Database(path).initialize()
    assert len(_backups(path)) == dbmod.MAX_MIGRATION_BACKUPS
