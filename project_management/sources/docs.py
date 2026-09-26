"""Lenient parsers for the coordination docs (ROADMAP, ACTIVE_WORK, DECISIONS, MEMORY).

These files are hand-written markdown; every parser degrades to "raw text" rather
than failing. Nothing here writes files.
"""

from __future__ import annotations

import re
from pathlib import Path

from .redact import redact

_MAX_DOC_BYTES = 512 * 1024


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()[:_MAX_DOC_BYTES]
    except OSError:
        return None
    return data.decode("utf-8-sig", "replace")


# ---------------------------------------------------------------- markdown helpers

def split_sections(text: str, level: int) -> list[tuple[str, str]]:
    """Split on headings of exactly ``level`` (#-count). Returns [(title, body)]; preamble has title ''."""
    marker = re.compile(rf"^{'#' * level}(?!#)\s+(.*?)\s*$", re.MULTILINE)
    out: list[tuple[str, str]] = []
    last_title, last_pos = "", 0
    for m in marker.finditer(text):
        out.append((last_title, text[last_pos:m.start()]))
        last_title, last_pos = m.group(1), m.end()
    out.append((last_title, text[last_pos:]))
    return [(t, b.strip("\n")) for t, b in out if t or b.strip()]


_CHECK_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$")


# ---------------------------------------------------------------- ROADMAP

_MILESTONE_RE = re.compile(r"^Milestone\s+(\d+)\s*[—\-:]\s*(.*)$", re.IGNORECASE)


def parse_roadmap(text: str | None) -> dict:
    if not text:
        return {"ok": False, "milestones": [], "current": None, "next": None}
    milestones = []
    for title, body in split_sections(text, 2):
        m = _MILESTONE_RE.match(title)
        if m:
            num, name = int(m.group(1)), m.group(2)
        elif title:
            num, name = None, title
        else:
            continue
        items, section = [], ""
        for line in body.splitlines():
            h = re.match(r"^#{3,}\s+(.*)$", line)
            if h:
                section = h.group(1).strip()
                continue
            c = _CHECK_RE.match(line)
            if c:
                items.append({"done": c.group(1).lower() == "x", "text": c.group(2).strip(), "section": section})
        main = [i for i in items if not i["section"]]
        follow = [i for i in items if i["section"]]
        marked_done = "✅" in name
        clean_name = re.sub(r"\s*✅.*$", "", name).strip()
        clean_name = re.sub(r"\s*\((?:NEXT|next)[^)]*\)\s*$", "", clean_name).strip()
        done_count = sum(i["done"] for i in main)
        milestones.append({
            "number": num,
            "title": clean_name,
            "heading": name,
            "total": len(main),
            "done_count": done_count,
            "items": main,
            "follow_ups": follow,
            "open_follow_ups": [i for i in follow if not i["done"]],
            "marked_done": marked_done,
            "status": "",
        })

    numbered = [m for m in milestones if m["number"] is not None]
    current = nxt = None
    for m in numbered:
        all_done = m["total"] > 0 and m["done_count"] == m["total"]
        if m["marked_done"]:
            m["status"] = "done"
        elif all_done:
            m["status"] = "ready_to_close"
            current = current or m["number"]
        elif m["done_count"] > 0:
            m["status"] = "in_progress"
            current = current or m["number"]
        else:
            m["status"] = "not_started"
    for m in numbered:
        if m["status"] == "not_started":
            nxt = m["number"]
            break
    if nxt is not None and current is None:
        for m in numbered:
            if m["number"] == nxt:
                m["status"] = "next"
    for m in milestones:
        if m["number"] is None:
            m["status"] = "other"
    return {"ok": True, "milestones": milestones, "current": current, "next": nxt}


# ---------------------------------------------------------------- ACTIVE_WORK

_WORKER_HEAD_RE = re.compile(r"^(W\d+)\s*[:：]\s*(.*?)(?:\.\s*Status\s*:\s*(.*))?$", re.IGNORECASE)


def parse_active_work(text: str | None) -> dict:
    if not text:
        return {"ok": False, "sections": [], "workers": [], "reservations": [], "raw": ""}
    sections = []
    workers = []
    reservations: list[str] = []
    for title, body in split_sections(text, 2):
        sections.append({"title": title, "body": redact(body)})
        if title.lower().startswith("workers"):
            for wtitle, wbody in split_sections(body, 3):
                m = _WORKER_HEAD_RE.match(wtitle)
                if not m:
                    continue
                status_text = (m.group(3) or "").strip()
                status_word = re.match(r"([A-Z_]+)", status_text)
                workers.append({
                    "id": m.group(1).upper(),
                    "title": m.group(2).strip(),
                    "status": status_word.group(1) if status_word else "UNKNOWN",
                    "status_text": status_text,
                    "bullets": [redact(b) for b in _bullets(wbody)],
                })
        elif title.lower().startswith("reservation"):
            reservations = [redact(b) for b in _bullets(body)]
    updated = re.search(r"^Last updated:\s*(.+)$", text, re.MULTILINE)
    return {
        "ok": True,
        "updated": updated.group(1).strip() if updated else None,
        "sections": sections,
        "workers": workers,
        "reservations": reservations,
        "raw": redact(text),
    }


def _bullets(body: str) -> list[str]:
    """Top-level bullet items, with their indented continuation lines joined."""
    out: list[str] = []
    for line in body.splitlines():
        if re.match(r"^[-*]\s+", line):
            out.append(re.sub(r"^[-*]\s+", "", line).strip())
        elif out and line.startswith((" ", "\t")) and line.strip():
            out[-1] += "\n" + line.strip()
    return out


# ---------------------------------------------------------------- DECISIONS / MEMORY

_ADR_RE = re.compile(r"^##\s+(ADR-(\d+))\s*[—\-:]\s*(.+?)\s*$", re.MULTILINE)


def parse_adrs(text: str | None) -> list[dict]:
    if not text:
        return []
    adrs = [{"id": m.group(1), "number": int(m.group(2)), "title": m.group(3)} for m in _ADR_RE.finditer(text)]
    return sorted(adrs, key=lambda a: a["number"])


def memory_current_state(text: str | None) -> dict:
    if not text:
        return {"ok": False, "phase": "", "bullets": []}
    phase = current = ""
    for title, body in split_sections(text, 2):
        low = title.lower()
        if low.startswith("current phase"):
            phase = body.strip()
        elif low.startswith("current state"):
            current = body
    return {"ok": True, "phase": redact(phase), "bullets": [redact(b) for b in _bullets(current)]}
