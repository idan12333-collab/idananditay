"""Daily summaries written by the PM: ``project_management/daily/YYYY-MM-DD.md``."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .redact import redact

_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
_MAX_FILES = 60
_MAX_BYTES = 64 * 1024


def load(daily_dir: Path, today: date | None = None) -> dict:
    today_s = (today or date.today()).isoformat()
    entries = []
    try:
        names = sorted((p.name for p in daily_dir.iterdir() if p.is_file()), reverse=True)
    except OSError:
        names = []
    for name in names:
        m = _NAME_RE.match(name)
        if not m:
            continue
        try:
            text = (daily_dir / name).read_bytes()[:_MAX_BYTES].decode("utf-8-sig", "replace")
        except OSError:
            continue
        entries.append({"date": m.group(1), "text": redact(text)})
        if len(entries) >= _MAX_FILES:
            break
    today_entry = next((e for e in entries if e["date"] == today_s), None)
    return {"today": today_s, "today_entry": today_entry, "history": [e for e in entries if e["date"] != today_s]}
