"""Read-only git access through a fixed allowlist of commands with fixed arguments.

No caller-supplied arguments ever reach git; there is no shell.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# name -> fixed argv (after "git -c core.quotepath=off")
ALLOWED: dict[str, tuple[str, ...]] = {
    "branch": ("rev-parse", "--abbrev-ref", "HEAD"),
    "head": ("rev-parse", "--short", "HEAD"),
    "log": ("log", "-n", "15", "--format=%h%x1f%aI%x1f%s"),
    "status": ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
    "diffstat": ("diff", "--numstat"),
}
_TIMEOUT_S = 10


class GitError(RuntimeError):
    pass


def run(name: str, repo: Path) -> str:
    if name not in ALLOWED:
        raise GitError(f"command not allowed: {name}")
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"      # never take the index lock other sessions use
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    argv = ["git", "-c", "core.quotepath=off", *ALLOWED[name]]
    try:
        proc = subprocess.run(
            argv, cwd=str(repo), capture_output=True, timeout=_TIMEOUT_S,
            shell=False, env=env, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"git failed: {exc.__class__.__name__}") from exc
    if proc.returncode != 0:
        raise GitError(proc.stderr.decode("utf-8", "replace").strip()[:300] or "git error")
    return proc.stdout.decode("utf-8", "replace")


def parse_status_z(out: str) -> list[dict]:
    """Parse ``git status --porcelain=v1 -z`` into [{path, code, kind}]."""
    items: list[dict] = []
    parts = out.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":          # rename/copy: next field is the source path
            i += 1
        if code == "??":
            kind = "new"
        elif "D" in code:
            kind = "deleted"
        elif "A" in code:
            kind = "added"
        elif code[0] in "RC":
            kind = "renamed"
        else:
            kind = "modified"
        items.append({"path": path.replace("\\", "/"), "code": code, "kind": kind,
                      "staged": code[0] not in " ?"})
    return items


def parse_numstat(out: str) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for line in out.splitlines():
        cols = line.split("\t")
        if len(cols) != 3:
            continue
        add, rem, path = cols
        stats[path.replace("\\", "/")] = {
            "added": int(add) if add.isdigit() else None,
            "removed": int(rem) if rem.isdigit() else None,
        }
    return stats


def parse_log(out: str) -> list[dict]:
    commits = []
    for line in out.splitlines():
        cols = line.split("\x1f")
        if len(cols) == 3:
            commits.append({"hash": cols[0], "at": cols[1], "subject": cols[2]})
    return commits


def snapshot(repo: Path) -> dict:
    """Everything the dashboard needs from git. Errors are reported, not raised."""
    result: dict = {"ok": True, "error": None}
    try:
        result["branch"] = run("branch", repo).strip()
        result["head"] = run("head", repo).strip()
        result["commits"] = parse_log(run("log", repo))
        files = parse_status_z(run("status", repo))
        stats = parse_numstat(run("diffstat", repo))
        for f in files:
            f.update(stats.get(f["path"], {"added": None, "removed": None}))
        result["dirty"] = files
        result["clean"] = not files
    except GitError as exc:
        result.update(ok=False, error=str(exc), branch=None, head=None, commits=[], dirty=[], clean=None)
    return result
