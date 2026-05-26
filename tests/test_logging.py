"""Structured logging: direct-print JSON / text emission + job_id contextvar.

The implementation deliberately bypasses Python's `logging` module — see
worker/logging.py docstring for the reasoning. These tests capture
stdout directly because that's the only output channel.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from contextlib import redirect_stdout

import pytest

import handler
from worker import logging as worker_logging


def _capture(callable_, *args, **kwargs) -> str:
    """Run a callable while capturing stdout. Returns the captured text."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        callable_(*args, **kwargs)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# JSON output (default)
# -----------------------------------------------------------------------------

def test_info_emits_one_line_json(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    out = _capture(worker_logging.info, "test message", backend="vlm-auto-engine", pages=10)
    assert out.count("\n") == 1
    data = json.loads(out.strip())
    assert data["msg"] == "test message"
    assert data["level"] == "info"
    assert data["logger"] == "mineru-worker"
    assert data["backend"] == "vlm-auto-engine"
    assert data["pages"] == 10
    assert data["ts"].endswith("Z")


def test_warning_and_error_use_correct_levels(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    warn_out = _capture(worker_logging.warning, "watch out")
    err_out = _capture(worker_logging.error, "kaboom", code=42)
    assert json.loads(warn_out)["level"] == "warning"
    err = json.loads(err_out)
    assert err["level"] == "error"
    assert err["code"] == 42


def test_debug_is_silent_by_default(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    out = _capture(worker_logging.debug, "noisy detail")
    assert out == ""  # debug is suppressed unless LOG_LEVEL=debug


def test_debug_enabled_when_log_level_debug(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    out = _capture(worker_logging.debug, "now you see me", detail="visible")
    data = json.loads(out.strip())
    assert data["level"] == "debug"
    assert data["detail"] == "visible"


def test_flush_happens_per_emission(monkeypatch, capsys):
    """RunPod docs warn about buffered output; we pass flush=True every call."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    worker_logging.info("first")
    worker_logging.info("second")
    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["msg"] == "first"
    assert json.loads(lines[1])["msg"] == "second"


# -----------------------------------------------------------------------------
# Text mode for local development
# -----------------------------------------------------------------------------

def test_text_format_is_human_readable(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    out = _capture(worker_logging.info, "hello", backend="pipeline", pages=42)
    assert "hello" in out
    assert "INFO" in out
    assert "[mineru-worker]" in out
    assert "backend=pipeline" in out
    assert "pages=42" in out


def test_log_format_read_per_call(monkeypatch):
    """LOG_FORMAT is read on every emission so tests can flip modes."""
    monkeypatch.setenv("LOG_FORMAT", "json")
    json_out = _capture(worker_logging.info, "first")
    monkeypatch.setenv("LOG_FORMAT", "text")
    text_out = _capture(worker_logging.info, "second")
    json.loads(json_out.strip())  # parses as JSON
    assert "INFO" in text_out  # not JSON


# -----------------------------------------------------------------------------
# job_id contextvar — auto-injected so cross-job correlation works.
# -----------------------------------------------------------------------------

def test_job_id_appears_in_json(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    token = worker_logging.job_id_var.set("test-job-abc-123")
    try:
        out = _capture(worker_logging.info, "hi")
        assert json.loads(out.strip())["job_id"] == "test-job-abc-123"
    finally:
        worker_logging.job_id_var.reset(token)


def test_job_id_appears_in_text(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    token = worker_logging.job_id_var.set("test-job-xyz-456")
    try:
        out = _capture(worker_logging.info, "hi")
        assert "job_id=test-job-xyz-456" in out
    finally:
        worker_logging.job_id_var.reset(token)


def test_job_id_omitted_when_unset(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    worker_logging.job_id_var.set(None)
    out = _capture(worker_logging.info, "hi")
    assert "job_id" not in json.loads(out.strip())


# -----------------------------------------------------------------------------
# End-to-end: handler() pins the contextvar and emits at least one log line
# -----------------------------------------------------------------------------

def _stub_run_mineru(monkeypatch):
    async def fake_run(file_bytes, *, basename, work_dir, **kwargs):
        out = work_dir / "out"
        out.mkdir()
        (out / f"{basename}.md").write_text("# fake\n", encoding="utf-8")
        return out
    monkeypatch.setattr("worker.parse.run_mineru", fake_run)


def test_handler_sets_job_id_contextvar(monkeypatch, capsys):
    """End-to-end: handler() pins job["id"] into the contextvar and log lines carry it."""
    _stub_run_mineru(monkeypatch)
    monkeypatch.setenv("LOG_FORMAT", "json")

    captured: dict = {}

    async def spy_handler(job):
        result = await handler.handler(job)
        captured["job_id_during_request"] = worker_logging.job_id_var.get()
        return result

    asyncio.run(spy_handler({
        "id": "queued-job-uuid-789",
        "input": {"file_b64": "JVBERi0xLjQK", "basename": "test"},
    }))

    assert captured["job_id_during_request"] == "queued-job-uuid-789"

    # The "starting job" line should be in stdout with the correct job_id.
    out = capsys.readouterr().out
    starting_lines = [
        json.loads(ln) for ln in out.splitlines()
        if ln.startswith("{") and '"starting job"' in ln
    ]
    assert starting_lines, "no 'starting job' log line emitted"
    assert starting_lines[0]["job_id"] == "queued-job-uuid-789"


def test_handler_uses_fallback_when_no_job_id(monkeypatch):
    """Sync clients without a queued job have no id; handler uses <unknown>."""
    _stub_run_mineru(monkeypatch)

    captured: dict = {}

    async def spy():
        await handler.handler({
            # No "id" key in the job dict.
            "input": {"file_b64": "JVBERi0xLjQK", "basename": "test"},
        })
        captured["job_id"] = worker_logging.job_id_var.get()

    asyncio.run(spy())
    assert captured["job_id"] == "<unknown>"
