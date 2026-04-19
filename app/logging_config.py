"""Structured logging with per-request trace_id propagation.

Two output modes controlled by `settings.log_format`:
  • "plain" — human-readable text incl. trace_id suffix
  • "json"  — one JSON object per line for log aggregators

`trace_id` is an ``asyncio.ContextVar`` — set once at the edge (HTTP
middleware for API, aiogram middleware for the bot) and read by the
logging filter. No explicit passing through call stacks.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any

_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


def new_trace_id(prefix: str = "") -> str:
    """Generate a short trace id, optionally prefixed (e.g. 'tg-', 'api-')."""
    tid = uuid.uuid4().hex[:12]
    return f"{prefix}{tid}" if prefix else tid


def set_trace_id(trace_id: str) -> object:
    """Bind `trace_id` to the current context. Returns the token for reset()."""
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: object) -> None:
    """Undo a previous set_trace_id; safe no-op if the token is stale."""
    try:
        _trace_id_var.reset(token)  # type: ignore[arg-type]
    except (ValueError, LookupError):
        pass


def get_trace_id() -> str:
    return _trace_id_var.get()


class _TraceIdFilter(logging.Filter):
    """Inject the current ContextVar value into every LogRecord as `trace_id`."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter — no extra dependencies."""

    # Standard LogRecord attributes — used to skip them when picking up
    # caller-supplied `extra=` fields.
    _RESERVED = frozenset({
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
        "trace_id",
    })

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": getattr(record, "trace_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Any additional fields attached via `logger.info(..., extra={...})`.
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key.startswith("_"):
                continue
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


_PLAIN_FMT = "%(asctime)s [%(levelname)s] [%(trace_id)s] %(name)s: %(message)s"
_DATE_FMT = "%H:%M:%S"


def setup_logging(level: str = "INFO", fmt: str = "plain") -> None:
    """Configure the root logger. Safe to call multiple times."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.addFilter(_TraceIdFilter())

    if fmt.lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_PLAIN_FMT, datefmt=_DATE_FMT))

    root.addHandler(handler)
