"""Application configuration.

Values come from (highest priority first): explicit constructor args, environment
variables with the ``APP_`` prefix, the project ``.env`` file, and defaults below.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    # Deliberately in the user's profile root, not in a synced folder
    # (Desktop/Documents are commonly synced by OneDrive), so derived data from
    # personal photos stays local.
    return Path.home() / ".ai-photo-album" / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=default_data_dir)

    host: str = "127.0.0.1"
    port: int = 8765
    # Host headers accepted by the API (protects the local server against DNS rebinding).
    allowed_hosts: list[str] = ["127.0.0.1", "localhost"]

    log_level: str = "INFO"
    log_json: bool = False

    # Ingestion
    ingest_workers: int = 0  # 0 = auto
    thumbnail_size: int = 480
    thumbnail_quality: int = 85
    analysis_max_side: int = 1024

    # Duplicates: Hamming distance on 64-bit hashes. Both must pass.
    near_dup_phash_threshold: int = 8
    near_dup_dhash_threshold: int = 12

    # Quality heuristics
    blur_threshold: float = 40.0
    low_res_min_megapixels: float = 1.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / "library.sqlite3"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    def effective_workers(self) -> int:
        if self.ingest_workers > 0:
            return self.ingest_workers
        return max(1, min(8, (os.cpu_count() or 2) - 1))

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.thumbnails_dir, self.logs_dir, self.exports_dir, self.cache_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
