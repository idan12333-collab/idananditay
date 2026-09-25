from app.core.config import Settings


def test_defaults_are_local_and_outside_project(monkeypatch):
    s = Settings(_env_file=None)
    assert s.host == "127.0.0.1"
    assert ".ai-photo-album" in str(s.data_dir)
    assert s.db_path.parent == s.data_dir
    assert s.effective_workers() >= 1


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_NEAR_DUP_PHASH_THRESHOLD", "5")
    monkeypatch.setenv("APP_INGEST_WORKERS", "3")
    s = Settings(_env_file=None)
    assert s.data_dir == tmp_path
    assert s.near_dup_phash_threshold == 5
    assert s.effective_workers() == 3
