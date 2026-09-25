from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.database import Database
from app.db.repository import Repository
from tests.fixtures import build_library


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        ingest_workers=1,
        allowed_hosts=["testserver", "127.0.0.1", "localhost"],
    )
    s.ensure_dirs()
    return s


@pytest.fixture
def repo(settings: Settings) -> Repository:
    db = Database(settings.db_path)
    db.initialize()
    return Repository(db)


@pytest.fixture(scope="session")
def library_template(tmp_path_factory) -> tuple[Path, dict[str, Path]]:
    root = tmp_path_factory.mktemp("lib_template") / "photos"
    return root, build_library(root)


@pytest.fixture
def library(tmp_path: Path, library_template) -> tuple[Path, dict[str, Path]]:
    """A fresh copy of the fixture library per test (tests may modify it)."""
    import shutil

    src_root, src_paths = library_template
    root = tmp_path / "photos"
    shutil.copytree(src_root, root)
    return root, {k: root / p.relative_to(src_root) for k, p in src_paths.items()}


def fingerprint(root: Path) -> dict[str, tuple[str, float]]:
    """sha256 + mtime of every file under root (to prove originals are untouched)."""
    return {
        str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
