"""Regression: starting the app while an OLDER copy still runs must not silently use the old copy.

Real incident (2026-09-26): after a fix, the owner re-ran start.bat while the pre-fix server was
still running. The launcher opened the browser, the new process migrated the DB and logged
"app started", then failed to bind port 8765 and exited. The browser kept talking to the old
process (old code, old cache headers) and showed a photo from another folder. See ADR-013.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

import app.__main__ as cli
from app.core.instance import APP_NAME, BUILD_ID, bind_server_socket, classify_existing, compute_build_id
from app.main import create_app

# /api/health exactly as the pre-fix build (the one the owner had running) answered it.
OLD_BUILD_HEALTH = {
    "status": "ok", "version": "0.1.0", "database": "ok", "heic_supported": True,
    "supported_extensions": [".heic", ".heif", ".jpeg", ".jpg", ".png", ".webp"],
}


def _fake_server(health: dict | None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if health is not None and self.path == "/api/health":
                body = json.dumps(health).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            else:
                body = b"<html>some other program</html>"
                self.send_response(404)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def opened(monkeypatch):
    urls: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url, *a, **k: urls.append(url))
    return urls


@pytest.fixture
def old_instance():
    srv = _fake_server(OLD_BUILD_HEALTH)
    yield srv.server_address[1]
    srv.shutdown()


def test_outdated_instance_on_port_blocks_start(settings, old_instance, opened, capsys):
    rc = cli.serve(settings, "127.0.0.1", old_instance, open_browser=True)
    assert rc == cli.EXIT_OUTDATED_INSTANCE
    assert opened == []  # the browser must NOT be pointed at the old copy
    assert not settings.db_path.exists()  # a process that cannot serve does no DB work (no migration)
    assert "OLDER copy" in capsys.readouterr().err


def test_same_build_instance_is_reused(settings, opened):
    srv = _fake_server({**OLD_BUILD_HEALTH, "app": APP_NAME, "build": BUILD_ID, "pid": 1})
    try:
        port = srv.server_address[1]
        assert cli.serve(settings, "127.0.0.1", port, open_browser=True) == 0
        assert opened == [f"http://127.0.0.1:{port}"]
        assert not settings.db_path.exists()
    finally:
        srv.shutdown()


def test_port_used_by_other_program(settings, opened):
    srv = _fake_server(None)
    try:
        assert cli.serve(settings, "127.0.0.1", srv.server_address[1], open_browser=True) == cli.EXIT_PORT_FOREIGN
        assert opened == []
    finally:
        srv.shutdown()


def test_port_bind_is_exclusive():
    first = bind_server_socket("127.0.0.1", 0)
    assert first is not None
    first.listen()
    try:
        assert bind_server_socket("127.0.0.1", first.getsockname()[1]) is None
    finally:
        first.close()


def test_classify_existing():
    assert classify_existing(None) == "foreign"
    assert classify_existing(OLD_BUILD_HEALTH) == "outdated"  # pre-update copies report no build
    assert classify_existing({"app": APP_NAME, "build": "other"}) == "outdated"
    assert classify_existing({"app": APP_NAME, "build": BUILD_ID}) == "same"


def test_build_id_changes_with_code(tmp_path):
    (tmp_path / "m.py").write_text("x = 1")
    before = compute_build_id(tmp_path)
    (tmp_path / "m.py").write_text("x = 2")
    assert compute_build_id(tmp_path) != before


def test_health_identifies_running_code(settings):
    with TestClient(create_app(settings)) as c:
        h = c.get("/api/health").json()
        assert h["app"] == APP_NAME and h["build"] == BUILD_ID and isinstance(h["pid"], int)
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert c.get("/static/app.js").headers["cache-control"] == "no-cache"


def test_cli_entry_point_refuses_outdated_instance(settings, old_instance, opened, monkeypatch):
    """Through `python -m app serve --open-browser`, exactly as start.bat runs it."""
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    rc = cli.main(["serve", "--port", str(old_instance), "--open-browser"])
    assert rc == cli.EXIT_OUTDATED_INSTANCE and opened == []
