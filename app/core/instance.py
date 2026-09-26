"""Single-instance guard for the local server (ADR-013).

Real incident (2026-09-26): the owner started the app while an older copy was still running.
The launcher opened the browser, the new process migrated the database and logged "app
started", then failed to bind the port and exited — so the browser kept talking to the OLD
process, which still ran pre-fix code. To prevent that:

* the port is bound *before* anything else happens (no DB work by a process that cannot serve);
* on Windows the bind is exclusive, so two servers can never share the port;
* if the port is taken, the existing server is identified via /api/health and its code
  ``build`` is compared with ours; an outdated copy is reported instead of silently used;
* the browser is opened only once *this* process is actually serving.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.request
from pathlib import Path

APP_NAME = "AI Photo Album"
_APP_DIR = Path(__file__).resolve().parents[1]
_BUILD_SUFFIXES = frozenset({".py", ".js", ".html", ".css"})


def compute_build_id(root: Path = _APP_DIR) -> str:
    """Fingerprint of the application code (Python + web UI files)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix in _BUILD_SUFFIXES and "__pycache__" not in p.parts:
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


# The code this process loaded at startup.
BUILD_ID = compute_build_id()


def bind_server_socket(host: str, port: int) -> socket.socket | None:
    """Bind the listening socket exclusively. Returns None if the port is already in use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: forbid any other socket on this port
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        return None
    return sock


def probe_existing(host: str, port: int, timeout: float = 3.0) -> dict | None:
    """Health info if the server on host:port is this app (any version), else None."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    # Versions before ADR-013 do not report "app"; they are recognised by their health fields.
    if body.get("app") == APP_NAME or {"heic_supported", "supported_extensions"} <= body.keys():
        return body
    return None


def classify_existing(info: dict | None, build_id: str = BUILD_ID) -> str:
    """'foreign' (not our app), 'same' (same code), or 'outdated' (older/different code)."""
    if info is None:
        return "foreign"
    return "same" if info.get("build") == build_id else "outdated"


def process_id() -> int:
    return os.getpid()
