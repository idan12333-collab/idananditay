"""Dev auto-reload supervisor (ADR-020): watch filter, debounce, safe restarts, restart mid-scan."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.db.database import Database
from app.db.repository import Repository
from app.services.jobs import JobManager

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("dev_supervisor", REPO_ROOT / "scripts" / "dev_supervisor.py")
sup = importlib.util.module_from_spec(_spec)
sys.modules["dev_supervisor"] = sup
_spec.loader.exec_module(sup)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ------------------------------------------------------------------ what is watched

def test_only_code_and_ui_files_are_watched(tmp_path):
    root = tmp_path / "app"
    watched = ["main.py", "web/static/app.js", "web/static/index.html", "web/static/styles.css"]
    ignored = [
        "__pycache__/main.cpython-312.pyc", "__pycache__/x.py", ".git/config.py", "tests/test_x.py",
        "library.sqlite3", "library.sqlite3-wal", "thumbnails/1.jpg", "thumbnails/x.py", "logs/app.log",
        "backups/b.sqlite3", "cache/c.py", "data/d.py", "~$main.py", ".~lock.main.py#", "main.py.tmp",
        "main.py~", "settings.json", "notes.md",
    ]
    for rel in watched + ignored:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    assert sorted(sup.snapshot(root)) == sorted(watched)


def test_default_targets_watch_only_the_two_code_trees():
    targets = sup.default_targets()
    assert {t.watch_root for t in targets.values()} == {REPO_ROOT / "app", REPO_ROOT / "project_management"}
    data_home = Path.home() / ".ai-photo-album"
    for t in targets.values():
        assert data_home not in t.watch_root.parents and t.watch_root != data_home


def test_snapshot_detects_an_edit(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("1", encoding="utf-8")
    before = sup.snapshot(tmp_path)
    f.write_text("22", encoding="utf-8")
    assert sup.snapshot(tmp_path) != before


def test_debounce_turns_a_burst_into_one_restart():
    d = sup.Debouncer(quiet=1.0)
    fired = 0
    # OneDrive/editor burst: 5 touches within ~0.8 s, polled every 0.1 s for 3 s.
    changes = {0.0, 0.2, 0.4, 0.6, 0.8}
    for i in range(31):
        now = round(i * 0.1, 1)
        if now in changes:
            d.note_change(now)
        fired += d.ready(now)
    assert fired == 1
    assert not d.ready(10.0)  # nothing pending afterwards


# ------------------------------------------------------------------ safe restarts

FAKE_SERVER = textwrap.dedent("""
    import json, os, socket, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer
    port = int(sys.argv[1])
    class S(HTTPServer):
        allow_reuse_address = False
        def server_bind(self):
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"build": "b", "pid": os.getpid(),
                               "dev_instance": os.environ.get("AI_ALBUM_DEV_INSTANCE")}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)
        def log_message(self, *a): pass
    try:
        httpd = S(("127.0.0.1", port), H)
    except OSError:
        sys.exit(4)  # like `python -m app serve` when it cannot own the port (ADR-013)
    httpd.serve_forever()
""")


@pytest.fixture
def fake_target(tmp_path):
    script = tmp_path / "fake_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    port = _free_port()
    t = sup.Target("fake", [sys.executable, str(script), str(port)], tmp_path, port, start_timeout=20)
    yield t
    if t.proc is not None:
        sup.stop_process(t.proc)


def test_restart_replaces_the_old_process(fake_target):
    t = fake_target
    assert sup.start(t)
    old = t.proc
    old_health = sup.health(t.host, t.port)
    assert old_health["dev_instance"] == t.token
    assert sup.restart(t)
    assert old.poll() is not None, "old server must have exited"
    new_health = sup.health(t.host, t.port)
    assert t.proc is not old and new_health["dev_instance"] == t.token != old_health["dev_instance"]
    assert new_health["pid"] != old_health["pid"]


def test_old_process_never_keeps_serving_when_new_one_fails_to_bind(fake_target, tmp_path):
    t = fake_target
    assert sup.start(t)
    old = t.proc
    # The new build cannot start (e.g. it fails to bind / crashes on import).
    t.cmd = [sys.executable, "-c", "import sys; sys.exit(4)"]
    assert not sup.restart(t)
    assert old.poll() is not None, "old server must be gone, not silently serving stale code"
    assert sup.health(t.host, t.port, timeout=0.5) is None
    assert "exited during startup" in t.last_error


def test_foreign_server_on_the_port_is_reported_not_trusted(fake_target):
    t = fake_target

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"build": "old", "pid": 999999}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", t.port), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        assert not sup.stop(t)  # port never frees up -> loud error, nothing started
        assert "still in use" in t.last_error
        # Even if started anyway, an answer from another pid is never accepted as "our new server".
        assert not sup.start(t)
        assert t.proc is None
    finally:
        httpd.shutdown()
        httpd.server_close()


# ------------------------------------------------------------------ restart in the middle of a scan

SLOW_SCAN_CHILD = textwrap.dedent("""
    import sys, time
    from pathlib import Path
    from app.core.config import Settings
    from app.db.database import Database
    from app.db.repository import Repository
    import app.services.jobs as jobs

    class HangingPipeline(jobs.IngestionPipeline):
        def run(self, library_id, progress=None, cancel=None):
            progress(phase="scanning", processed=1)
            print("SCANNING", flush=True)
            time.sleep(600)

    jobs.IngestionPipeline = HangingPipeline
    s = Settings(_env_file=None, data_dir=Path(sys.argv[1]), ingest_workers=1)
    s.ensure_dirs()
    db = Database(s.db_path); db.initialize()
    repo = Repository(db, s.print_policy())
    lib = repo.create_library(sys.argv[2], "lib")
    job = jobs.JobManager(s, repo).start_scan(lib["id"])
    print("JOB", job["id"], lib["id"], flush=True)
    time.sleep(600)
""")


def test_restart_mid_scan_never_leaves_scan_completed(settings, library):
    root, _ = library
    proc = subprocess.Popen(
        [sys.executable, "-c", SLOW_SCAN_CHILD, str(settings.data_dir), str(root)],
        cwd=REPO_ROOT, stdout=subprocess.PIPE, text=True, env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    try:
        job_id = lib_id = None
        seen_scanning = False
        for line in proc.stdout:
            if line.startswith("JOB"):
                _, job_id, lib_id = line.split()
            seen_scanning |= line.startswith("SCANNING")
            if job_id and seen_scanning:
                break
        assert job_id and seen_scanning, "child never reached the scan"
    finally:
        assert sup.stop_process(proc)  # exactly how the dev supervisor stops a server

    repo = Repository(Database(settings.db_path), settings.print_policy())
    assert repo.get_job(job_id)["status"] == "running"  # killed mid-scan

    jm = JobManager(settings, repo)  # = the restarted server starting up
    job = repo.get_job(job_id)
    assert job["status"] == "interrupted"
    assert job["status"] not in ("done", "completed")

    # Safely re-runnable: a new scan of the same library completes and indexes the photos.
    new = jm.start_scan(int(lib_id))
    assert new["id"] != job_id
    assert jm.wait(new["id"], timeout=120)["status"] == "done"
    assert repo.get_job(job_id)["status"] == "interrupted"
    assert repo.library_stats(int(lib_id))["indexed"] > 0


# ------------------------------------------------------------------ page auto-reload hooks

def test_app_page_auto_reloads_only_in_dev_mode(settings, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.delenv(sup.DEV_ENV_VAR, raising=False)
    with TestClient(create_app(settings)) as c:
        assert "app-dev-reload" not in c.get("/").text
    monkeypatch.setenv(sup.DEV_ENV_VAR, "1")
    with TestClient(create_app(settings)) as c:
        assert '<meta name="app-dev-reload" content="1">' in c.get("/").text


def test_dashboard_health_reports_build_and_pid():
    import urllib.request

    from project_management import server

    httpd = server.make_server(port=0, transcripts_dir=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/api/health", timeout=5) as r:
            h = json.loads(r.read())
        assert h["build"] == server.BUILD_ID and h["pid"] == os.getpid() and h["dev_reload"] is False
    finally:
        httpd.shutdown()
        httpd.server_close()
