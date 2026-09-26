"""Redaction of secret-looking values before anything reaches the browser."""

from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]{8,}"),
    re.compile(
        r"(?i)\b([A-Za-z_]*(?:api[_-]?key|token|secret|password|passwd|pwd|credential)[A-Za-z_]*)"
        r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
    ),
    # Long opaque blobs (keys, base64 secrets). 40+ chars without spaces, mixed classes.
    re.compile(r"(?<![A-Za-z0-9/+_\-])(?=[A-Za-z0-9+/_\-]*\d)(?=[A-Za-z0-9+/_\-]*[A-Za-z])[A-Za-z0-9+/_\-]{40,}={0,2}"),
]

MASK = "[מוסתר]"


def redact(text: str | None) -> str:
    if not text:
        return ""
    out = str(text)
    for pat in _PATTERNS:
        if pat.groups >= 3:
            out = pat.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", out)
        else:
            out = pat.sub(MASK, out)
    return out


def is_secret_path(path: str) -> bool:
    """True for files whose content/name must never be shown (e.g. ``.env``)."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if name == ".env.example":
        return False
    return (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith((".pem", ".key"))
        or name in {"id_rsa", "id_ed25519", "credentials.json"}
    )
