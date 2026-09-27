"""Create the owner's seed sample for quick labeling (ADR-022, evaluation/SEED_WORKER_BRIEF.md).

Reads the app database READ-ONLY and writes the sample JSON (default: <data>/seed/seed_sample_lib<id>.json,
where the "תיוג מהיר" screen looks for it). The same sample can also be created from the screen itself.
The file contains the owner's photo IDs and hashes: keep it out of git.

    python evaluation/make_seed_sample.py --library 1 [--seed 20260926] [--out path] [--force]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings  # noqa: E402
from app.curation import seed as seed_sample  # noqa: E402
from app.db.database import Database  # noqa: E402
from app.db.repository import Repository  # noqa: E402


class ReadOnlyDatabase(Database):
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--library", type=int, required=True, help="library ID (see the app's library list)")
    ap.add_argument("--seed", type=int, default=seed_sample.DEFAULT_SEED)
    ap.add_argument("--db", type=Path, help="database path (default: the app's data dir)")
    ap.add_argument("--out", type=Path, help="output JSON (default: where the app looks for it)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing sample")
    args = ap.parse_args(argv)

    settings = Settings()
    db_path = args.db or settings.db_path
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 2
    out = args.out or seed_sample.sample_path(settings.data_dir, args.library)
    if out.exists() and not args.force:
        print(f"A sample already exists: {out} (use --force to replace it)", file=sys.stderr)
        return 1
    repo = Repository(ReadOnlyDatabase(db_path), settings.print_policy())
    if repo.get_library(args.library) is None:
        print(f"No library with ID {args.library}", file=sys.stderr)
        return 2
    sample = seed_sample.build_sample(repo, args.library, args.seed)
    seed_sample.save_sample(out, sample)
    print(f"Wrote {len(sample['items'])} items to {out}")
    print(f"counts: {sample['counts']}")
    if sample["shortfall"]:
        print(f"short strata (the library has fewer photos than asked): {sample['shortfall']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
