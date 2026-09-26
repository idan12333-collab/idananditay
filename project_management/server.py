"""Local HTTP server for the project-management dashboard (stdlib only).

Security model (see README): 127.0.0.1 only, strict Host allowlist, same-origin
JSON-only POSTs, static files from one fixed directory, no shell, read-only git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import PACKAGE_DIR, REPO_ROOT
from .dashboard import Dashboard
from .sources import inbox

DEFAULT_PORT = 8790
DEV_RELOAD = os.environ.get("AI_ALBUM_DEV_RELOAD") == "1"  # set only by scripts/dev_supervisor.py (ADR-020)


def compute_build_id(root: Path = PACKAGE_DIR) -> str:
    """Fingerprint of the dashboard code (tests and runtime data excluded)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if (p.is_file() and p.suffix in {".py", ".js", ".html", ".css"}
                and not {"__pycache__", "tests"} & set(p.relative_to(root).parts)):
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


BUILD_ID = compute_build_id()
WEB_DIR = PACKAGE_DIR / "web"
MAX_BODY = 16 * 1024
STATIC_FILES = {  # URL path -> (file name in WEB_DIR, content type). Nothing else is served.
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class _Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind the same port and silently
    # shadow the first (see ADR-013). Bind exclusively instead.
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version = "PMDashboard/1"
    sys_version = ""
    dashboard: Dashboard  # set by make_server
    port: int

    # --------------------------------------------------------------- helpers
    def log_request(self, code="-", size="-") -> None:  # quiet console: log failures only
        if str(getattr(code, "value", code)).startswith(("4", "5")):
            super().log_request(code, size)

    def _allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, msg: str) -> None:
        self._json(status, {"error": msg})

    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "").strip().lower() in self._allowed_hosts()

    # --------------------------------------------------------------- verbs
    def do_GET(self) -> None:
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "host not allowed")
        path = self.path.split("?", 1)[0]
        if path == "/api/health":  # which copy of the code answers (dev auto-reload, ADR-020)
            return self._json(HTTPStatus.OK, {"status": "ok", "app": "PM Dashboard", "build": BUILD_ID,
                                              "pid": os.getpid(), "dev_reload": DEV_RELOAD,
                                              "dev_instance": os.environ.get("AI_ALBUM_DEV_INSTANCE")})
        if path == "/api/dashboard":
            return self._json(HTTPStatus.OK, self.dashboard.build())
        if path in STATIC_FILES:
            name, ctype = STATIC_FILES[path]
            try:
                body = (WEB_DIR / name).read_bytes()
            except OSError:
                return self._error(HTTPStatus.NOT_FOUND, "not found")
            return self._send(HTTPStatus.OK, body, ctype)
        return self._error(HTTPStatus.NOT_FOUND, "not found")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        if not self._host_ok():
            return self._error(HTTPStatus.FORBIDDEN, "host not allowed")
        if self.headers.get("Sec-Fetch-Site", "").lower() not in {"same-origin", "none"}:
            return self._error(HTTPStatus.FORBIDDEN, "cross-site request rejected")
        origin = self.headers.get("Origin")
        if origin and origin.lower() not in {f"http://{h}" for h in self._allowed_hosts()}:
            return self._error(HTTPStatus.FORBIDDEN, "origin not allowed")
        if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
            return self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "JSON required")
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            return self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body too large")
        path = self.path.split("?", 1)[0]
        if path != "/api/request":
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._error(HTTPStatus.BAD_REQUEST, "invalid JSON")
        if not isinstance(data, dict):
            return self._error(HTTPStatus.BAD_REQUEST, "invalid JSON")
        names = self.dashboard.known_workers()
        try:
            item = inbox.append(
                self.dashboard.inbox_path,
                str(data.get("type") or ""), str(data.get("worker") or ""), str(data.get("text") or ""),
                set(names),
            )
        except inbox.InboxError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        item["copy_text"] = inbox.copy_text(item, names)
        return self._json(HTTPStatus.CREATED, item)

    def _reject(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _reject


def make_server(port: int = DEFAULT_PORT, repo: Path = REPO_ROOT, pm_dir: Path = PACKAGE_DIR,
                transcripts_dir: Path | None | bool = True) -> ThreadingHTTPServer:
    dash = Dashboard(repo, pm_dir, transcripts_dir)
    handler = type("BoundHandler", (Handler,), {"dashboard": dash, "port": port})
    httpd = _Server(("127.0.0.1", port), handler)
    if port == 0:  # tests: bind an ephemeral port, then allow exactly that one
        handler.port = httpd.server_address[1]
    return httpd


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AI Album — project-management dashboard (local only)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):   # a cp1252 console must not crash on Hebrew
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        httpd = make_server(args.port)
    except OSError:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"הפורט {args.port} כבר תפוס — כנראה שהדשבורד כבר פתוח. פותח את {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 1
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"לוח הבקרה של הפרויקט פועל: {url}  (לסגירה: סגור את החלון הזה או Ctrl+C)")
    if not args.no_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
