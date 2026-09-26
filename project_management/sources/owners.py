"""Group dirty files by owning worker (via ``owns[]`` globs) and raise warnings."""

from __future__ import annotations

import re
from functools import lru_cache

PM_ID = "PM"


@lru_cache(maxsize=512)
def _glob_re(pattern: str) -> re.Pattern:
    """Glob → regex. ``**`` spans directories, ``*``/``?`` do not; a trailing ``/`` means the whole dir."""
    p = pattern.strip().replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    if p.endswith("/"):
        p += "**"
    out, i = [], 0
    while i < len(p):
        c = p[i]
        if p.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif p.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


def matches(path: str, pattern: str) -> bool:
    if not pattern.strip():
        return False
    return bool(_glob_re(pattern).match(path.replace("\\", "/")))


def group_dirty(dirty: list[dict], workers: list[dict], pm_owns: list[str]) -> dict:
    """Return {groups: {owner_id: [file]}, shared: [...], unowned: [...], warnings: [...]}.

    A file may belong to several owners (e.g. a worker's doc hunks in MEMORY.md,
    which the PM also owns). Warnings:
      * ``mixed``   – dirty files belong to more than one worker (PM docs excluded)
      * ``shared``  – a single file is owned by more than one worker (hunk-level split needed)
      * ``unowned`` – dirty files nobody owns
    """
    owners: list[tuple[str, list[str]]] = [(w["id"], w.get("owns") or []) for w in workers]
    owners.append((PM_ID, pm_owns or []))

    groups: dict[str, list[dict]] = {}
    shared: list[dict] = []
    unowned: list[dict] = []
    for f in dirty:
        who = [oid for oid, globs in owners if any(matches(f["path"], g) for g in globs)]
        entry = {**f, "owners": who}
        if not who:
            unowned.append(entry)
            continue
        for oid in who:
            groups.setdefault(oid, []).append(entry)
        worker_owners = [o for o in who if o != PM_ID]
        if len(worker_owners) > 1:
            shared.append(entry)

    warnings: list[dict] = []
    workers_with_dirty = sorted(oid for oid in groups if oid != PM_ID)
    if len(workers_with_dirty) > 1:
        warnings.append({
            "type": "mixed", "level": "warn", "workers": workers_with_dirty,
            "text_hebrew": "יש שינויים שלא נשמרו (commit) של יותר מעובד אחד. "
                           "כל עובד חייב לבצע commit רק לקבצים/חלקים שלו.",
        })
    if shared:
        warnings.append({
            "type": "shared", "level": "info", "files": [f["path"] for f in shared],
            "text_hebrew": "קבצים משותפים לכמה עובדים — ה-commit צריך להיות לפי חלקים (hunks), בזהירות.",
        })
    if unowned:
        warnings.append({
            "type": "unowned", "level": "warn", "files": [f["path"] for f in unowned],
            "text_hebrew": "יש קבצים ששונו ואין להם בעלים לפי המצב של המנהל.",
        })
    return {"groups": groups, "shared": shared, "unowned": unowned, "warnings": warnings}

