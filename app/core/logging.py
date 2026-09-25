"""Structured logging.

Use ``log_event(logger, "message", key=value, ...)`` to attach structured context.
Console output is human-readable key=value; the log file is JSON lines.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler

from app.core.config import Settings

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = getattr(record, "ctx", None)
        if ctx:
            payload.update(ctx)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.name}: {record.getMessage()}"
        ctx = getattr(record, "ctx", None)
        if ctx:
            line += " " + " ".join(f"{k}={v}" for k, v in ctx.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(settings: Settings) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    # Windows consoles may not be UTF-8; never crash on Hebrew paths in log lines.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    root = logging.getLogger("app")
    root.setLevel(settings.log_level.upper())
    root.propagate = False

    console = logging.StreamHandler()
    console.setFormatter(JsonFormatter() if settings.log_json else KeyValueFormatter())
    root.addHandler(console)

    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        settings.logs_dir / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name.startswith("app") else f"app.{name}")


def log_event(logger: logging.Logger, msg: str, level: int = logging.INFO, **ctx) -> None:
    logger.log(level, msg, extra={"ctx": ctx})
