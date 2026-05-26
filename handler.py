"""RunPod serverless entry point for the MinerU worker.

The pieces this orchestrates live in the worker/ package:
  worker.schema   — input validation
  worker.io       — fetch raw bytes from URL / b64 / volume + format detection
  worker.parse    — MinerU lazy import + async parse call
  worker.package  — tarball / inline / s3 response packaging
  worker.debug    — GPU info, model dir, /runpod-volume probe
  worker.logging  — JSON / text structured logging

The module surface (``handler.MAX_INLINE_FILE_MB``, ``handler._detect_format``,
``handler._validate_input``, ``handler._package_tarball``, etc.) is preserved
for tests/back-compat — see the re-exports near the bottom of this file.
"""

from __future__ import annotations

import os
import signal
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import runpod

from worker import debug as _debug
from worker import io as _io
from worker import logging as _logging
from worker import package as _package
from worker import parse as _parse
from worker import schema as _schema


# -----------------------------------------------------------------------------
# Graceful shutdown
# -----------------------------------------------------------------------------
#
# RunPod sends SIGTERM when recycling a worker (idle timeout, refresh, manual
# stop). The SDK already drains in-flight jobs, but the user-visible signal
# tends to be "worker logs go silent." We install a breadcrumb handler + a
# shutdown event that the handler checks between phases — so a request that's
# between fetch_input and parse can bail out instead of consuming GPU time
# that's about to be killed anyway. Mid-parse cancellation is NOT possible
# (vLLM forward pass is a blocking GPU call from asyncio's POV).

_shutting_down = threading.Event()


def _on_sigterm(signum: int, frame: Any) -> None:  # noqa: ARG001
    _logging.warning("sigterm received, draining current job")
    _shutting_down.set()


# Install at module init. RunPod's SDK may install its own handler when
# runpod.serverless.start() runs; in that case our handler is replaced and
# this becomes a no-op breadcrumb that never fires. Acceptable — failure is
# silent and the rest of the worker is unaffected.
try:
    signal.signal(signal.SIGTERM, _on_sigterm)
except (ValueError, OSError) as e:  # pragma: no cover — non-main-thread case
    _logging.warning("could not install sigterm handler", error=repr(e))


def _check_shutdown() -> None:
    """Raise if SIGTERM has been received. Called between request phases."""
    if _shutting_down.is_set():
        raise RuntimeError("worker shutting down, refusing further work")


# -----------------------------------------------------------------------------
# Cumulative refresh counters
# -----------------------------------------------------------------------------
#
# Recycle this worker after N cumulative jobs or M cumulative pages so that
# MinerU + vLLM accumulated VRAM fragmentation gets released. Opt-in via env
# vars; both default to 0 (disabled). When a threshold trips, the handler
# attaches `refresh_worker: True` to the response — RunPod's SDK then kills
# the worker after the response is sent.
#
# Pages counter only increments when the caller used a bounded slice
# (end_page >= 0). Full-document parses (end_page=-1, the default) contribute
# 1 to jobs but 0 to pages — documented in scaling.mdx so operators know to
# use the jobs counter for unbounded workloads.

_jobs_processed = 0
_pages_processed_total = 0
_refresh_lock = threading.Lock()


def _refresh_thresholds() -> tuple[int, int]:
    """Read thresholds from env on every job so they can be tuned without redeploy."""
    try:
        jobs = int(os.environ.get("REFRESH_WORKER_AFTER_JOBS", "0"))
    except ValueError:
        jobs = 0
    try:
        pages = int(os.environ.get("REFRESH_WORKER_AFTER_PAGES", "0"))
    except ValueError:
        pages = 0
    return max(0, jobs), max(0, pages)


def _record_job(pages: int) -> bool:
    """Bump counters; return True if a refresh threshold was crossed.

    ``pages`` is the requested slice size (positive) or 0 for unbounded /
    unknown — only the jobs counter increments in the unbounded case.
    """
    global _jobs_processed, _pages_processed_total
    with _refresh_lock:
        _jobs_processed += 1
        if pages > 0:
            _pages_processed_total += pages
        jobs_th, pages_th = _refresh_thresholds()
        return (jobs_th > 0 and _jobs_processed >= jobs_th) or \
               (pages_th > 0 and _pages_processed_total >= pages_th)


# -----------------------------------------------------------------------------
# Concurrency
# -----------------------------------------------------------------------------
#
# vLLM pre-allocates a large KV cache and isn't safe to drive from concurrent
# aio_do_parse calls on smaller GPUs. Default 1 is safe on every supported
# GPU type. Operators with ≥24 GB GPUs may raise via MINERU_MAX_CONCURRENCY.
# See guides/scaling.mdx for the VRAM math.

def _concurrency_modifier(current_concurrency: int) -> int:  # noqa: ARG001
    try:
        return max(1, int(os.environ.get("MINERU_MAX_CONCURRENCY", "1")))
    except ValueError:
        return 1


# -----------------------------------------------------------------------------
# Progress + debug envelope
# -----------------------------------------------------------------------------

def _maybe_progress(job: dict, data: dict) -> None:
    """Best-effort progress update. Tests / sync clients without a job id
    shouldn't fail just because we tried to surface progress."""
    try:
        runpod.serverless.progress_update(job, data)
    except Exception as e:  # noqa: BLE001
        _logging.debug("progress_update failed", error=repr(e))


def _build_debug(phase_ms: dict[str, int], gpu_info: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "gpu": gpu_info,
        "model_dir": _debug.find_model_dir(),
        "phase_ms": phase_ms,
        **extra,
    }


async def _handle_probe(started: float, gpu_info: dict[str, Any], phase_ms: dict[str, int]) -> dict[str, Any]:
    _logging.info("probe job: dumping filesystem layout")
    return {
        "ok": True,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "mineru_version": _parse.MINERU_VERSION,
        "mineru_available": _parse.MINERU_AVAILABLE,
        "probe": _debug.probe_filesystem(),
        "debug": _build_debug(phase_ms, gpu_info),
    }


async def _handle_parse(
    job: dict,
    cleaned: dict[str, Any],
    started: float,
    gpu_info: dict[str, Any],
    phase_ms: dict[str, int],
) -> dict[str, Any]:
    # rp_validator's strict typing forces end_page to be an int; translate
    # the -1 sentinel back to None so MinerU treats it as "until end of doc".
    end_page_val = cleaned["end_page"]
    end_page = None if end_page_val is None or end_page_val < 0 else int(end_page_val)
    backend = cleaned["backend"]

    _logging.info(
        "starting job",
        backend=backend,
        lang=cleaned["lang"],
        start_page=cleaned["start_page"],
        end_page=end_page,
        gpu_name=gpu_info.get("name"),
        compute_capability=gpu_info.get("compute_capability"),
    )

    _check_shutdown()
    _maybe_progress(job, {"phase": "fetching_input"})
    t = time.monotonic()
    file_bytes, source = await _io.resolve_input_bytes(cleaned)
    phase_ms["fetch_input"] = int((time.monotonic() - t) * 1000)

    input_format = _io.detect_format(file_bytes)
    if input_format == "unknown":
        raise ValueError(
            "input bytes do not match any supported format "
            "(PDF, PNG/JPEG/GIF/BMP/TIFF/WebP image, or DOCX/PPTX/XLSX). "
            "Check that file_b64 was base64-encoded correctly and that "
            "file_url returned the file body (not an error page)."
        )

    _check_shutdown()
    _maybe_progress(job, {
        "phase": "parsing",
        "input_bytes": len(file_bytes),
        "input_format": input_format,
        "start_page": cleaned["start_page"],
        "end_page": end_page,
    })

    with tempfile.TemporaryDirectory(prefix="mineru-job-") as tmp:
        work_dir = Path(tmp)
        t = time.monotonic()
        output_dir = await _parse.run_mineru(
            file_bytes,
            basename=cleaned["basename"],
            work_dir=work_dir,
            input_format=input_format,
            start_page=cleaned["start_page"],
            end_page=end_page,
            lang=cleaned["lang"],
            backend=backend,
            server_url=cleaned.get("server_url"),
            formula_enable=cleaned["formula_enable"],
            table_enable=cleaned["table_enable"],
        )
        phase_ms["mineru_parse"] = int((time.monotonic() - t) * 1000)

        _check_shutdown()
        _maybe_progress(job, {"phase": "packaging"})

        t = time.monotonic()
        # `pages_requested` reflects the slice the caller asked for, NOT the
        # number MinerU actually produced (MinerU may emit fewer if the doc
        # is shorter than end_page). -1 == "full document".
        pages_requested = (
            (end_page - cleaned["start_page"] + 1) if end_page is not None else -1
        )
        response: dict[str, Any] = {
            "ok": True,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "pages_requested": pages_requested,
            "pages_processed": pages_requested,  # back-compat alias
            "mineru_version": _parse.MINERU_VERSION,
            "source": source,
        }
        if cleaned["return"] == "inline":
            response.update(_package.package_inline(output_dir, cleaned["basename"]))
        elif cleaned["return"] == "s3":
            response.update(_package.package_s3(output_dir, cleaned["basename"]))
        else:
            response["tarball_b64"] = _package.package_tarball(output_dir)
        phase_ms["package"] = int((time.monotonic() - t) * 1000)

        response["debug"] = _build_debug(
            phase_ms, gpu_info, backend=backend, input_format=input_format
        )

        # Cumulative refresh check — outside the lock so logging happens after
        # the counter bump. Bounded slices contribute their page count;
        # unbounded ones contribute 0 to the pages tally (jobs still +1).
        bumped_pages = pages_requested if pages_requested > 0 else 0
        if _record_job(bumped_pages):
            response["refresh_worker"] = True
            _logging.info(
                "refresh threshold crossed; signaling worker recycle",
                jobs_processed=_jobs_processed,
                pages_processed_total=_pages_processed_total,
            )

        _logging.info(
            "done",
            elapsed_seconds=response["elapsed_seconds"],
            phase_ms=phase_ms,
            model_dir=response["debug"]["model_dir"],
            refresh_worker=response.get("refresh_worker", False),
        )
        return response


async def handler(job: dict) -> dict:
    started = time.monotonic()
    phase_ms: dict[str, int] = {}
    gpu_info = _debug.collect_gpu_info()
    # Pin the job id into the logging contextvar so every line emitted
    # from this request carries `job_id` for correlation (per RunPod's
    # write-logs guidance). Falls back to "<unknown>" if RunPod doesn't
    # surface an id (sync clients without a queued job).
    _logging.job_id_var.set(job.get("id") or "<unknown>")
    try:
        raw_input = job.get("input") or {}
        # Probe mode bypasses schema validation: a probe has no file source
        # and the operator may want to send arbitrary debug flags through.
        if raw_input.get("probe") is True:
            return await _handle_probe(started, gpu_info, phase_ms)

        cleaned = _schema.validate_input(raw_input)
        return await _handle_parse(job, cleaned, started, gpu_info, phase_ms)

    except Exception as exc:  # noqa: BLE001
        # Top-level `error` key tells RunPod to mark this job FAILED.
        # Keep `ok=false` and the structured details so clients see context.
        _logging.error(
            "job failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
            phase_ms=phase_ms,
        )
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "ok": False,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "mineru_version": _parse.MINERU_VERSION,
            "traceback": traceback.format_exc(limit=5),
            "debug": _build_debug(phase_ms, gpu_info),
        }


# -----------------------------------------------------------------------------
# Back-compat surface for tests and any out-of-tree callers that imported
# helpers from this module directly. New code should import from worker.*.
# -----------------------------------------------------------------------------

MAX_INLINE_FILE_MB = _io.MAX_INLINE_FILE_MB
MINERU_VERSION = _parse.MINERU_VERSION
_MINERU_AVAILABLE = _parse.MINERU_AVAILABLE

_resolve_input_bytes = _io.resolve_input_bytes
_detect_format = _io.detect_format
_validate_input = _schema.validate_input
_package_tarball = _package.package_tarball
_package_inline = _package.package_inline
_package_s3 = _package.package_s3
_build_tarball_bytes = _package._build_tarball_bytes
_run_mineru = _parse.run_mineru
_collect_gpu_info = _debug.collect_gpu_info
_find_model_dir = _debug.find_model_dir
_probe_filesystem = _debug.probe_filesystem


if __name__ == "__main__":
    runpod.serverless.start({
        "handler": handler,
        "concurrency_modifier": _concurrency_modifier,
    })
