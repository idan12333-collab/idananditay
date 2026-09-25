"""Command line: ``python -m app serve`` | ``python -m app scan <folder>``."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="AI Photo Album (local MVP)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve = sub.add_parser("serve", help="Run the local web app")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)

    scan = sub.add_parser("scan", help="Index a photo folder and print a summary")
    scan.add_argument("folder")
    scan.add_argument("--workers", type=int, default=0)

    args = parser.parse_args(argv)

    from app.core.config import get_settings
    from app.core.logging import configure_logging

    settings = get_settings()
    configure_logging(settings)

    if args.cmd == "serve":
        import uvicorn

        from app.main import create_app

        uvicorn.run(create_app(settings), host=args.host or settings.host, port=args.port or settings.port,
                    log_level=settings.log_level.lower())
        return 0

    if args.cmd == "scan":
        from pathlib import Path

        from app.db.database import Database
        from app.db.repository import Repository
        from app.ingest.pipeline import IngestionPipeline

        if args.workers:
            settings.ingest_workers = args.workers
        settings.ensure_dirs()
        db = Database(settings.db_path)
        db.initialize()
        repo = Repository(db)
        root = Path(args.folder).expanduser().resolve()
        if not root.is_dir():
            print(f"Folder not found: {root}", file=sys.stderr)
            return 2
        lib = repo.create_library(str(root), root.name)
        summary = IngestionPipeline(settings, repo).run(lib["id"])
        print(json.dumps({"summary": summary.to_dict(), "stats": repo.library_stats(lib["id"])},
                         indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
