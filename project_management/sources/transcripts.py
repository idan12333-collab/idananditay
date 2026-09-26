"""Read-only adapter for Claude Code session transcripts (``~/.claude/projects/<dir>/*.jsonl``).

The transcript format is undocumented, so ALL knowledge of it lives in this one
module and everything degrades to "no data" on surprises.

Privacy rules enforced here (tests cover them):
  * thinking / reasoning blocks are never read into the output;
  * tool inputs are never emitted — only the tool name, a repo-relative path for
    file tools, and a coarse classification for shell commands (never the command);
  * tool results are never emitted, except a matched test-summary line;
  * visible assistant text is truncated and redacted;
  * secret-looking files (``.env``) are masked by name.

Context size is an *estimate*: the last main-thread assistant message's
``input + cache_creation + cache_read`` tokens over ``CONTEXT_WINDOW_TOKENS``.
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePath

from .redact import is_secret_path, redact

CONTEXT_WINDOW_TOKENS = 1_000_000
_MAX_ACTIVITY = 40
_MAX_TEXT = 200
_MAX_FILES = 40
_MAX_LINE = 2 * 1024 * 1024
_TEST_LINE_RE = re.compile(
    r"(?:^|[=\s])(\d+ (?:passed|failed)(?:, \d+ (?:passed|failed|skipped|errors?|warnings?|deselected|xfailed|xpassed))*"
    r"(?: in [\d.]+s)?)",
)


def project_dir_name(repo: Path) -> str:
    """Claude Code names the project folder after the cwd with every non-alphanumeric char → '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(repo))


def default_transcripts_dir(repo: Path) -> Path | None:
    override = os.environ.get("PM_TRANSCRIPTS_DIR")
    if override:
        p = Path(override)
        return p if p.is_dir() else None
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    p = home / ".claude" / "projects" / project_dir_name(repo)
    return p if p.is_dir() else None


# ---------------------------------------------------------------- per-file incremental state

class _FileState:
    __slots__ = ("offset", "size", "mtime", "session_id", "titles", "latest_title",
                 "last_at", "usage_tokens", "usage_at", "activity", "last_text", "turns", "last_msg_id")

    def __init__(self) -> None:
        self.offset = 0
        self.size = -1
        self.mtime = 0.0
        self.session_id: str | None = None
        self.titles: set[str] = set()
        self.latest_title: str | None = None
        self.last_at: str | None = None
        self.usage_tokens: int | None = None
        self.usage_at: str | None = None
        self.activity: deque = deque(maxlen=_MAX_ACTIVITY)
        self.last_text: dict | None = None
        self.turns: deque = deque(maxlen=3000)   # timestamps of main-thread assistant API responses
        self.last_msg_id: str | None = None


def _rel_path(raw: object, repo: Path) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        p = PurePath(raw)
        try:
            rel = Path(raw).resolve().relative_to(repo.resolve())
            shown = rel.as_posix()
        except (ValueError, OSError):
            shown = "(מחוץ לפרויקט) " + p.name
    except (TypeError, ValueError):
        return None
    if is_secret_path(shown):
        return "[קובץ סודות]"
    return redact(shown)


def _classify_shell(cmd: object) -> str:
    c = cmd.lower() if isinstance(cmd, str) else ""
    if "pytest" in c or "run_tests" in c:
        return "הריץ בדיקות"
    if re.search(r"\bgit\s+commit\b", c):
        return "ביצע commit"
    if re.search(r"\bgit\b", c):
        return "פקודת git"
    return "הריץ פקודה"


_FILE_TOOLS = {"Edit": "ערך את", "MultiEdit": "ערך את", "Write": "כתב את", "NotebookEdit": "ערך את"}
_QUIET_TOOLS = {"Read", "Grep", "Glob", "ToolSearch", "TodoWrite", "ListAgents"}


def _tool_activity(block: dict, repo: Path) -> dict | None:
    name = block.get("name")
    if not isinstance(name, str):
        return None
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    if name in _FILE_TOOLS:
        path = _rel_path(inp.get("file_path") or inp.get("notebook_path"), repo)
        return {"kind": "edit", "tool": name, "path": path, "text": f"{_FILE_TOOLS[name]} {path or 'קובץ'}"}
    if name in {"Bash", "PowerShell"}:
        return {"kind": "shell", "tool": name, "path": None, "text": _classify_shell(inp.get("command"))}
    if name == "SendMessage":
        to = inp.get("to") if isinstance(inp.get("to"), str) else ""
        to = re.sub(r"\s*\[[^\]]*\]$", "", to)[:60]
        if re.match(r"^[a-z]+:", to):          # raw transport address (uds:\\.\pipe\…), not a name
            to = "סשן אחר"
        return {"kind": "message", "tool": name, "path": None, "text": f"שלח הודעה ל-{redact(to) or '?'}"}
    if name in _QUIET_TOOLS:
        return None
    short = name.split("__")[-1] if name.startswith("mcp__") else name
    return {"kind": "tool", "tool": short[:60], "path": None, "text": f"השתמש בכלי {short[:60]}"}


def _process_entry(d: dict, st: _FileState, repo: Path) -> None:
    etype = d.get("type")
    if isinstance(d.get("sessionId"), str):
        st.session_id = d["sessionId"]
    if etype == "custom-title" and isinstance(d.get("customTitle"), str):
        st.titles.add(d["customTitle"])
        st.latest_title = d["customTitle"]
        return
    if etype == "agent-name" and isinstance(d.get("agentName"), str):
        st.titles.add(d["agentName"])
        st.latest_title = st.latest_title or d["agentName"]
        return
    if etype not in {"assistant", "user"}:
        return
    if d.get("isSidechain") is True:   # sub-agent traffic: not this session's own context
        return
    at = d.get("timestamp") if isinstance(d.get("timestamp"), str) else None
    if at:
        st.last_at = at
    msg = d.get("message") if isinstance(d.get("message"), dict) else {}
    content = msg.get("content")
    blocks = content if isinstance(content, list) else []

    if etype == "assistant":
        mid = msg.get("id") if isinstance(msg.get("id"), str) else None
        if at and (mid is None or mid != st.last_msg_id):   # one response may span several lines
            st.turns.append(at)
        st.last_msg_id = mid
        usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
        if usage:
            tot = 0
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                v = usage.get(k)
                if isinstance(v, int) and v >= 0:
                    tot += v
            if tot > 0:
                st.usage_tokens, st.usage_at = tot, at
        for b in blocks:
            if not isinstance(b, dict):
                continue
            btype = b.get("type")
            if btype == "text" and isinstance(b.get("text"), str) and b["text"].strip():
                txt = redact(" ".join(b["text"].split()))
                if len(txt) > _MAX_TEXT:
                    txt = txt[:_MAX_TEXT].rstrip() + "…"
                st.last_text = {"at": at, "text": txt}
            elif btype == "tool_use":
                act = _tool_activity(b, repo)
                if act:
                    act["at"] = at
                    st.activity.append(act)
            # "thinking" / "redacted_thinking" and anything else: deliberately ignored
    else:  # user: only look for a test summary inside tool results
        for b in blocks:
            if not isinstance(b, dict) or b.get("type") != "tool_result":
                continue
            line = _test_summary(b.get("content"))
            if line:
                st.activity.append({"kind": "tests", "tool": None, "path": None, "at": at,
                                    "text": f"תוצאת בדיקות: {line}",
                                    "failed": " failed" in line})


def _test_summary(content: object) -> str | None:
    if isinstance(content, list):
        content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and isinstance(c.get("text"), str))
    if not isinstance(content, str) or ("passed" not in content and "failed" not in content):
        return None
    found = None
    for m in _TEST_LINE_RE.finditer(content[-20000:]):
        found = m.group(1)
    return found


def _update_file(path: Path, st: _FileState, repo: Path) -> None:
    try:
        stat = path.stat()
    except OSError:
        return
    if stat.st_size == st.size and stat.st_mtime == st.mtime:
        return
    if stat.st_size < st.offset:          # rewritten/truncated: start over
        fresh = _FileState()
        for slot in _FileState.__slots__:
            setattr(st, slot, getattr(fresh, slot))
    try:
        with path.open("rb") as fh:
            fh.seek(st.offset)
            data = fh.read()
    except OSError:
        return
    end = data.rfind(b"\n")
    if end < 0:
        st.size, st.mtime = stat.st_size, stat.st_mtime
        return
    for raw in data[: end + 1].split(b"\n"):
        if not raw.strip() or len(raw) > _MAX_LINE:
            continue
        try:
            d = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict):
            try:
                _process_entry(d, st, repo)
            except Exception:  # noqa: BLE001 - undocumented format: never let one line break the page
                continue
    st.offset += end + 1
    st.size, st.mtime = stat.st_size, stat.st_mtime


class TranscriptReader:
    """Incrementally reads transcripts; cheap to call on every dashboard poll."""

    def __init__(self, transcripts_dir: Path | None, repo: Path) -> None:
        self.dir = transcripts_dir
        self.repo = repo
        self._files: dict[Path, _FileState] = {}
        self._lock = threading.Lock()

    def refresh(self) -> list[_FileState]:
        if not self.dir:
            return []
        try:
            paths = sorted(self.dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:_MAX_FILES]
        except OSError:
            return []
        with self._lock:
            for p in paths:
                st = self._files.setdefault(p, _FileState())
                _update_file(p, st, self.repo)
            return [self._files[p] for p in paths]

    def for_titles(self, titles: list[str]) -> dict | None:
        """Summary for the newest transcript whose (current or former) title matches."""
        if not titles:
            return None
        wanted = {t.strip() for t in titles if t.strip()}
        for st in self.refresh():              # newest first
            if st.titles & wanted:
                return summarize(st)
        return None


def _turns_since(st: _FileState, now: datetime, minutes: int) -> int:
    cutoff = now - timedelta(minutes=minutes)
    n = 0
    for at in reversed(st.turns):
        try:
            t = datetime.fromisoformat(at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t < cutoff:
            break
        n += 1
    return n


def summarize(st: _FileState, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    pct = None
    if st.usage_tokens:
        pct = round(min(100.0, st.usage_tokens * 100.0 / CONTEXT_WINDOW_TOKENS), 1)
    return {
        "title": st.latest_title,
        "last_activity_at": st.last_at,
        "context_estimate": {"percent": pct, "tokens": st.usage_tokens, "at": st.usage_at} if pct is not None else None,
        "activity": list(reversed(st.activity))[:20],
        "last_text": st.last_text,
        "turns_last_hour": _turns_since(st, now, 60),
    }
