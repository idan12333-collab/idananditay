"""Append-only request inbox (``project_management/inbox.jsonl``).

The dashboard cannot control Claude sessions; a request is a prepared message the
owner pastes into the Project Manager session. The PM marks requests handled by
listing their ids in ``state.json`` → ``inbox_handled``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

MAX_TEXT = 2000
_LOCK = threading.Lock()

# type -> (needs_worker, Hebrew label, message template)
REQUEST_TYPES: dict[str, tuple[bool, str, str]] = {
    "status_request":     (False, "בקשת עדכון מצב", "תן לי עדכון מצב{w_of}."),
    "pause_worker":       (True, "עצירת עובד", "עצור את {w} בנקודה בטוחה."),
    "continue_worker":    (True, "המשך עובד", "המשך את {w}."),
    "message_worker":     (True, "הודעה לעובד", "העבר ל{w}: {text}"),
    "manual_test_passed": (True, "בדיקה ידנית עברה", "הבדיקה הידנית של {w} עברה בהצלחה."),
    "manual_test_failed": (True, "בדיקה ידנית נכשלה", "הבדיקה הידנית של {w} נכשלה."),
    "new_task":           (False, "משימה / רעיון חדש", "משימה או רעיון חדש: {text}"),
    "summarize":          (False, "סכם לי מה קורה", "סכם לי בקצרה ובעברית פשוטה מה קורה בפרויקט עכשיו."),
    "daily_summary":      (False, "צור סיכום יום", "צור סיכום יום להיום ושמור אותו ב-project_management/daily."),
    "new_worker":         (False, "בקשה לעובד חדש", "צור עובד חדש עבור: {text}"),
}


class InboxError(ValueError):
    pass


def read_all(path: Path, handled: set[int] | None = None) -> list[dict]:
    handled = handled or set()
    items: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict) or not isinstance(d.get("id"), int):
            continue
        d["status"] = "handled" if d["id"] in handled else "pending"
        items.append(d)
    return items


def copy_text(item: dict, worker_names: dict[str, str]) -> str:
    rtype = item.get("type", "")
    _, _, template = REQUEST_TYPES.get(rtype, (False, "", "{text}"))
    wid = item.get("worker") or ""
    wname = worker_names.get(wid, wid)
    body = template.format(
        w=wname or "העובד",
        w_of=f" על {wname}" if wname else "",
        text=item.get("text") or "",
    )
    note = item.get("text") or ""
    if note and "{text}" not in template:
        body += f" הערה: {note}"
    return f"[בקשה מהדשבורד #{item.get('id')}] {body}"


def append(path: Path, rtype: str, worker: str, text: str, known_workers: set[str]) -> dict:
    if rtype not in REQUEST_TYPES:
        raise InboxError("סוג בקשה לא מוכר")
    needs_worker, _, template = REQUEST_TYPES[rtype]
    worker = (worker or "").strip()
    text = (text or "").strip()
    if len(text) > MAX_TEXT:
        raise InboxError("הטקסט ארוך מדי")
    if worker and worker not in known_workers:
        raise InboxError("עובד לא מוכר")
    if needs_worker and not worker:
        raise InboxError("יש לבחור עובד")
    if "{text}" in template and not text:
        raise InboxError("יש לכתוב טקסט")
    with _LOCK:
        existing = read_all(path)
        new_id = max((i["id"] for i in existing), default=0) + 1
        item = {
            "id": new_id,
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "type": rtype,
            "worker": worker,
            "text": text,
            "status": "pending",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item
