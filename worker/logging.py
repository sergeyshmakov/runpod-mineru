"""Structured logging for the worker, via direct prints to stdout.

We deliberately do NOT use Python's `logging` module here. Empirically,
the runpod SDK's serverless runtime reconfigures the root logger inside
`runpod.serverless.start()` in ways that silently swallow records from
loggers configured before it. Direct `print(..., flush=True)` is the
only reliable channel — RunPod captures stdout regardless of what any
logging library does to it (proven by the SDK's own `Started.` /
`Finished.` lines using the same mechanism).

Output is one JSON object per line by default — easier to filter in
RunPod's log viewer or any downstream JSON sink. ``LOG_FORMAT=text``
flips to a human-readable single-line format for local development.

A ``job_id`` ContextVar is auto-injected into every emission, per
RunPod's write-logs guidance ("Include the job ID or request ID in
log entries for traceability").
"""

from __future__ import annotations

import contextvars
import json
import os
import sys
import time
from typing import Any


# Set by handler.handler() at the top of each request; read on every
# emission. ContextVars are asyncio-safe — concurrent jobs in the same
# event loop don't bleed into each other's context.
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mineru_job_id", default=None
)


def _format_json(level: str, msg: str, fields: dict[str, Any]) -> str:
    """Build a one-line JSON record. Always includes ts, level, logger, msg."""
    now = time.time()
    ms = int((now - int(now)) * 1000)
    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + f".{ms:03d}Z",
        "level": level,
        "logger": "mineru-worker",
        "msg": msg,
    }
    if (jid := job_id_var.get()) is not None:
        record["job_id"] = jid
    record.update(fields)
    return json.dumps(record, default=str)


def _format_text(level: str, msg: str, fields: dict[str, Any]) -> str:
    """Compact human-readable single-line format."""
    ts = time.strftime("%H:%M:%S")
    parts = [f"{ts} {level.upper():<5} [mineru-worker] {msg}"]
    if (jid := job_id_var.get()) is not None:
        parts.append(f"job_id={jid}")
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    return " ".join(parts)


def _emit(level: str, msg: str, fields: dict[str, Any]) -> None:
    """Write one log line to stdout. Re-reads LOG_FORMAT each call so it
    can be flipped at runtime without restarting (mostly useful for tests)."""
    fmt = os.environ.get("LOG_FORMAT", "json").lower()
    line = _format_text(level, msg, fields) if fmt == "text" else _format_json(level, msg, fields)
    print(line, file=sys.stdout, flush=True)


def info(msg: str, **fields: Any) -> None:
    _emit("info", msg, fields)


def warning(msg: str, **fields: Any) -> None:
    _emit("warning", msg, fields)


def error(msg: str, **fields: Any) -> None:
    _emit("error", msg, fields)


def debug(msg: str, **fields: Any) -> None:
    # Only emit debug if explicitly enabled. Most of the time these are
    # too noisy for production but useful for local triage.
    if os.environ.get("LOG_LEVEL", "info").lower() == "debug":
        _emit("debug", msg, fields)
