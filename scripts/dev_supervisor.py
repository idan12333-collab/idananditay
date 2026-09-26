"""Dev-mode auto-reload supervisor (ADR-020). Stdlib only; developer tooling, not the product.

Runs the album app (port 8765) and/or the project-management dashboard (port 8790) as child
processes and restarts a child when one of ITS code/UI files changes:

    change detected -> debounce (a burst of saves / OneDrive touches = one restart)
    -> kill the old child -> verify it has EXITED and the port is FREE
    -> start a new child -> verify /api/health answers with the NEW child's instance token.

If any step fails it says so loudly and leaves nothing stale serving: the old child is always
gone before a new one starts (ADR-012/013 — the "old copy keeps answering" bug). A scan killed
by a restart ends as 'interrupted' (JobManager marks stale jobs at startup) and can be re-run.

Only .py/.html/.js/.css files under app/ and project_management/ are watched — never the
database, thumbnails, logs, caches, backups, .git, __pycache__ or OneDrive temp files (the
data lives in ~/.ai-photo-album, outside the watched trees).

Usage:  python scripts/dev_supervisor.py [--only app|dashboard] [--no-browser]
Normal start.bat / start_project_manager.bat are unaffected.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WATCH_SUFFIXES = frozenset({".py", ".html", ".js", ".css"})
# Directory names never descended into (caches, VCS, tests, runtime data).
SKIP_DIRS = frozenset({"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
                       "tests", "daily", "data", "logs", "thumbnails", "backups", "cache"})
DEV_ENV_VAR = "AI_ALBUM_DEV_RELOAD"  # tells the child to auto-reload its page on a build change
# A fresh random token per start, echoed by /api/health: proves the answer comes from THIS child.
# (A pid check is not enough: on Windows a venv python.exe is a launcher that runs the real
# interpreter as a grandchild with another pid.)
INSTANCE_ENV_VAR = "AI_ALBUM_DEV_INSTANCE"
POLL_SECONDS = 0.5
QUIET_SECONDS = 1.0  # restart only once the tree has been quiet this long


def is_watched_file(path: Path) -> bool:
    name = path.name
    if path.suffix.lower() not in WATCH_SUFFIXES:
        return False
    # Editor / OneDrive temporary names (e.g. "~$app.py", ".~lock.x.py", "#x.py#").
    return not name.startswith(("~", ".", "#"))


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """{relative path: (mtime_ns, size)} for every watched file under root."""
    out: dict[str, tuple[int, int]] = {}
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            p = Path(dirpath, fn)
            if not is_watched_file(p):
                continue
            try:
                st = p.stat()
            except OSError:  # vanished between listing and stat (save-by-rename)
                continue
            out[p.relative_to(root).as_posix()] = (st.st_mtime_ns, st.st_size)
    return out


class Debouncer:
    """Collapses a burst of changes into one event, fired after QUIET seconds of silence."""

    def __init__(self, quiet: float = QUIET_SECONDS):
        self.quiet = quiet
        self._last_change: float | None = None

    def note_change(self, now: float) -> None:
        self._last_change = now

    def ready(self, now: float) -> bool:
        if self._last_change is not None and now - self._last_change >= self.quiet:
            self._last_change = None
            return True
        return False


def port_is_free(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def health(host: str, port: int, timeout: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
        return body if isinstance(body, dict) else None
    except Exception:
        return None


def stop_process(proc: subprocess.Popen, timeout: float = 10.0) -> bool:
    """Kill the child AND its descendants outright (a dev server has nothing to flush); wait.

    No graceful shutdown: a scan in progress must not get the chance to write "done" — it is
    left 'running' and the next server start marks it 'interrupted' (JobManager)."""
    if os.name == "nt":
        # /T: the whole tree (the venv launcher's real-python grandchild is the actual server).
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    return True


@dataclass
class Target:
    name: str
    cmd: list[str]
    watch_root: Path
    port: int
    host: str = "127.0.0.1"
    url_path: str = "/"
    env: dict[str, str] = field(default_factory=dict)
    start_timeout: float = 60.0
    proc: subprocess.Popen | None = None
    token: str = ""
    last_error: str = ""

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{self.url_path}"


def _say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:  # a legacy console codepage must never crash the supervisor
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _fail(t: Target, en: str, he: str) -> bool:
    t.last_error = en
    bar = "!" * 70
    _say(f"\n{bar}\n[{t.name}] ERROR: {en}\n[{t.name}] שגיאה: {he}\n{bar}\n")
    return False


def stop(t: Target) -> bool:
    """Stop t's child and prove it is gone: process exited AND port free."""
    if t.proc is not None:
        if not stop_process(t.proc):
            return _fail(t, f"old server (pid {t.proc.pid}) did not exit", "השרת הישן לא נסגר")
        t.proc = None
    deadline = time.monotonic() + 10
    while not port_is_free(t.host, t.port):
        if time.monotonic() > deadline:
            return _fail(t, f"port {t.port} is still in use by another program (maybe start.bat is open?)",
                         f"הפורט {t.port} עדיין תפוס. אולי חלון רגיל של האפליקציה פתוח? סגרו אותו.")
        time.sleep(0.2)
    return True


def start(t: Target) -> bool:
    """Start a new child and verify that IT (its instance token) answers /api/health."""
    t.token = uuid.uuid4().hex
    env = {**os.environ, **t.env, DEV_ENV_VAR: "1", INSTANCE_ENV_VAR: t.token, "PYTHONUNBUFFERED": "1"}
    t.proc = subprocess.Popen(t.cmd, cwd=REPO_ROOT, env=env)
    deadline = time.monotonic() + t.start_timeout
    while time.monotonic() < deadline:
        code = t.proc.poll()
        if code is not None:
            t.proc = None
            return _fail(t, f"new server exited during startup (code {code}); fix the error above and save again",
                         "השרת החדש לא עלה. תקנו את השגיאה שמופיעה למעלה ושמרו שוב.")
        info = health(t.host, t.port)
        if info is not None:
            if info.get("dev_instance") == t.token:
                _say(f"[{t.name}] running build {info.get('build')} (pid {info.get('pid')}) at {t.url}")
                t.last_error = ""
                return True
            stop_process(t.proc)
            t.proc = None
            return _fail(t, f"port {t.port} answered from another server (pid {info.get('pid')}), not the new one",
                         f"תוכנה אחרת עונה בפורט {t.port}. סגרו חלונות אחרים של האפליקציה.")
        time.sleep(0.2)
    stop_process(t.proc)
    t.proc = None
    return _fail(t, "new server did not answer /api/health in time", "השרת החדש לא הגיב בזמן")


def restart(t: Target) -> bool:
    _say(f"[{t.name}] code changed - restarting...")
    return stop(t) and start(t)


def default_targets(python: str = sys.executable) -> dict[str, Target]:
    return {
        "app": Target("app", [python, "-m", "app", "serve", "--port", "8765"], REPO_ROOT / "app", 8765),
        "dashboard": Target("dashboard", [python, "-m", "project_management.server", "--port", "8790", "--no-browser"],
                            REPO_ROOT / "project_management", 8790),
    }


def run(targets: list[Target], open_browser: bool = True, max_loops: int | None = None) -> None:
    snaps = {t.name: snapshot(t.watch_root) for t in targets}
    debouncers = {t.name: Debouncer() for t in targets}
    loops = 0
    try:  # whatever happens, never leave child servers running behind us
        for t in targets:
            if stop(t) and start(t) and open_browser:
                webbrowser.open(t.url)
        _say("\nDev mode: watching code files. Save a file and the server restarts; the page reloads itself.\n"
             "מצב פיתוח: שמירת קובץ קוד מפעילה מחדש את השרת והדף מתרענן לבד. לסגירה: סגרו את החלון.\n")
        while max_loops is None or loops < max_loops:
            loops += 1
            time.sleep(POLL_SECONDS)
            now = time.monotonic()
            for t in targets:
                new = snapshot(t.watch_root)
                if new != snaps[t.name]:
                    snaps[t.name] = new
                    debouncers[t.name].note_change(now)
                if debouncers[t.name].ready(now):
                    restart(t)
                elif t.proc is not None and t.proc.poll() is not None:
                    code = t.proc.returncode
                    t.proc = None
                    _fail(t, f"server stopped unexpectedly (code {code}); save a file to retry",
                          "השרת נעצר. שמרו קובץ כדי לנסות שוב.")
    finally:
        for t in targets:
            if t.proc is not None:
                stop_process(t.proc)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Dev auto-reload for the album app and the PM dashboard (ADR-020)")
    ap.add_argument("--only", choices=["app", "dashboard"])
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # a cp1252 console must not crash on Hebrew
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    targets = default_targets()
    chosen = [targets[args.only]] if args.only else list(targets.values())
    try:
        run(chosen, open_browser=not args.no_browser)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
