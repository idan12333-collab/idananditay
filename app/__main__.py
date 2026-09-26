"""Command line: ``python -m app serve`` | ``python -m app scan <folder>``."""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="AI Photo Album (local MVP)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve_cmd = sub.add_parser("serve", help="Run the local web app")
    serve_cmd.add_argument("--host")
    serve_cmd.add_argument("--port", type=int)
    serve_cmd.add_argument("--open-browser", action="store_true", help="Open the UI once the server is up")

    scan = sub.add_parser("scan", help="Index a photo folder and print a summary")
    scan.add_argument("folder")
    scan.add_argument("--workers", type=int, default=0)

    args = parser.parse_args(argv)

    from app.core.config import get_settings
    from app.core.logging import configure_logging

    settings = get_settings()
    configure_logging(settings)

    if args.cmd == "serve":
        return serve(settings, args.host or settings.host, args.port or settings.port, args.open_browser)

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


EXIT_PORT_FOREIGN = 3
EXIT_OUTDATED_INSTANCE = 4


def serve(settings, host: str, port: int, open_browser: bool = False) -> int:
    """Start the local server — only if this process can own the port (ADR-013)."""
    import threading
    import webbrowser

    import uvicorn

    from app.core.instance import BUILD_ID, bind_server_socket, classify_existing, probe_existing

    url = f"http://{host}:{port}"
    sock = bind_server_socket(host, port)
    if sock is None:
        info = probe_existing(host, port)
        kind = classify_existing(info)
        if kind == "same":
            print(f"AI Photo Album is already running (same version) at {url}")
            if open_browser:
                webbrowser.open(url)
            return 0
        if kind == "outdated":
            print(
                f"\nERROR: an OLDER copy of AI Photo Album is still running at {url}\n"
                f"  (running build: {info.get('build') or 'pre-update'}, this build: {BUILD_ID}).\n"
                "  Close the old app window (or stop that process) and start the app again.\n"
                "  The new version was NOT started, so the browser was not opened.\n"
                "\nשגיאה: גרסה ישנה של האפליקציה עדיין פועלת. סגרו את החלון הישן והפעילו שוב.",
                file=sys.stderr,
            )
            return EXIT_OUTDATED_INSTANCE
        print(f"\nERROR: port {port} is used by another program. Set APP_PORT to a free port.", file=sys.stderr)
        return EXIT_PORT_FOREIGN

    from app.main import create_app

    config = uvicorn.Config(create_app(settings), host=host, port=port, log_level=settings.log_level.lower())
    server = uvicorn.Server(config)

    if open_browser:
        def open_when_ready() -> None:
            while not server.started and not server.should_exit:
                threading.Event().wait(0.1)
            if server.started:
                webbrowser.open(url)

        threading.Thread(target=open_when_ready, daemon=True).start()

    print(f"AI Photo Album (build {BUILD_ID}) is running at {url}  (close this window to stop)")
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main())
