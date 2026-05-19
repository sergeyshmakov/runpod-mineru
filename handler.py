"""RunPod serverless worker for MinerU 2.5 PDF parsing.

Generic — knows nothing about any particular calling project. Accepts a PDF
from one of three transports (URL / inline base64 / mounted-volume path),
parses with MinerU 2.5's VLM backend, and returns the output either as a
base64-encoded tarball or inline.

API contract (job input)
------------------------
Exactly one of:
    pdf_url      : str           — public or presigned HTTP(S) URL
    pdf_b64      : str           — base64-encoded PDF bytes (≤ 20 MB; RunPod gateway cap)
    volume_path  : str           — absolute path to a PDF inside the container
                                    (a mounted RunPod volume, or a file baked into the image)

Optional:
    start_page    : int = 0      — 0-based, inclusive
    end_page      : int          — 0-based, inclusive; omit / -1 = end of document
    lang          : str = "en"   — language hint passed to MinerU
    backend       : str          — MinerU backend, default "vlm-vllm-async-engine"
    formula_enable: bool = True
    table_enable  : bool = True
    return        : str          — "tarball_b64" (default) | "inline"
    basename      : str = "doc"  — filename stem for output files

Response on success
-------------------
    {
      "ok": true,
      "elapsed_seconds": 18.4,
      "pages_processed": 100,
      "mineru_version": "2.5.x",
      "source": "url:https://...",
      "tarball_b64": "..."         // or markdown/content_list/middle/images for inline
    }

Response on failure (RunPod marks job FAILED via the top-level `error` key)
--------------------------------------------------------------------------
    {
      "error": "ValueError: must provide exactly one of pdf_url / pdf_b64 / volume_path",
      "ok": false,
      "elapsed_seconds": 0.1,
      "mineru_version": "2.5.x",
      "traceback": "..."
    }
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import tarfile
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

import httpx
import runpod
from runpod.serverless.utils.rp_validator import validate


# MinerU's heavy imports run lazily inside _run_mineru so the handler module
# itself imports on a CPU-only test machine (CI exercises input validation
# and packaging without needing a GPU). Module-level only does a soft probe
# so we can report MINERU_VERSION even if the dep failed to install.
try:
    import mineru as _mineru
    from mineru.cli.common import aio_do_parse  # noqa: F401  (smoke import)
    MINERU_VERSION = getattr(_mineru, "__version__", "unknown")
    _MINERU_AVAILABLE = True
except Exception as e:  # pragma: no cover — handler returns the error to caller
    _mineru = None  # type: ignore[assignment]
    aio_do_parse = None  # type: ignore[assignment]
    MINERU_VERSION = f"import-failed: {e}"
    _MINERU_AVAILABLE = False


# RunPod's gateway caps payloads at 10 MB (/run) and 20 MB (/runsync). The
# 20 MB ceiling is the largest a caller can realistically send inline; the
# handler enforces it defensively but oversized requests are normally
# rejected at the gateway before reaching us. For larger files, use
# pdf_url or volume_path.
MAX_INLINE_PDF_MB = 20


# -----------------------------------------------------------------------------
# Input schema (rp_validator) — type coercion + bounds for the easy fields.
# The "exactly one of pdf_url/pdf_b64/volume_path" rule is enforced manually
# below because rp_validator doesn't express XOR.
# -----------------------------------------------------------------------------

INPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "pdf_url":        {"type": str,  "required": False, "default": None},
    "pdf_b64":        {"type": str,  "required": False, "default": None},
    "volume_path":    {"type": str,  "required": False, "default": None},
    "start_page":     {"type": int,  "required": False, "default": 0,
                       "constraints": lambda x: x >= 0},
    "end_page":       {"type": int,  "required": False, "default": -1},
    "lang":           {"type": str,  "required": False, "default": "en"},
    "backend":        {"type": str,  "required": False, "default": "vlm-vllm-async-engine"},
    "formula_enable": {"type": bool, "required": False, "default": True},
    "table_enable":   {"type": bool, "required": False, "default": True},
    "return":         {"type": str,  "required": False, "default": "tarball_b64",
                       "constraints": lambda x: x in {"tarball_b64", "inline"}},
    "basename":       {"type": str,  "required": False, "default": "doc",
                       "constraints": lambda x: bool(x) and all(
                           c.isalnum() or c in "-_" for c in x)},
}


_VALID_RETURNS = {"tarball_b64", "inline"}


def _validate_input(job_input: dict) -> dict:
    """Run rp_validator over the schema and enforce the cross-field rules."""
    result = validate(job_input, INPUT_SCHEMA)
    if result.get("errors"):
        raise ValueError(f"input validation failed: {'; '.join(result['errors'])}")

    cleaned = result["validated_input"]

    # rp_validator's `constraints` lambdas are silently ignored on some
    # versions — explicitly re-check the ones that matter for safety / shape.
    basename = cleaned.get("basename") or "doc"
    if not basename or not all(c.isalnum() or c in "-_" for c in basename):
        raise ValueError(
            f"input validation failed: basename must be alphanumeric (with - or _); "
            f"got {basename!r}"
        )

    ret = cleaned.get("return") or "tarball_b64"
    if ret not in _VALID_RETURNS:
        raise ValueError(
            f"input validation failed: return must be one of {sorted(_VALID_RETURNS)}; "
            f"got {ret!r}"
        )

    start_page = cleaned.get("start_page", 0) or 0
    if start_page < 0:
        raise ValueError(
            f"input validation failed: start_page must be >= 0; got {start_page!r}"
        )

    sources = [k for k in ("pdf_url", "pdf_b64", "volume_path") if cleaned.get(k)]
    if len(sources) != 1:
        raise ValueError(
            f"must provide exactly one of pdf_url / pdf_b64 / volume_path "
            f"(got {sources!r})"
        )
    return cleaned


# -----------------------------------------------------------------------------
# Input → PDF bytes
# -----------------------------------------------------------------------------

async def _resolve_pdf_bytes(job_input: dict) -> tuple[bytes, str]:
    """Return (pdf_bytes, source_label). Raises ValueError on bad input."""
    # Legacy path used by the test suite: it calls _resolve_pdf_bytes directly
    # with a raw payload. Keep that behaviour by re-deriving the source here
    # rather than relying on the validated dict.
    sources = {
        "pdf_url": job_input.get("pdf_url"),
        "pdf_b64": job_input.get("pdf_b64"),
        "volume_path": job_input.get("volume_path"),
    }
    provided = [k for k, v in sources.items() if v]
    if len(provided) != 1:
        raise ValueError(
            f"must provide exactly one of pdf_url / pdf_b64 / volume_path "
            f"(got {provided!r})"
        )
    key = provided[0]
    value = sources[key]

    if key == "pdf_url":
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(value, follow_redirects=True)
            resp.raise_for_status()
            return resp.content, f"url:{value}"

    if key == "pdf_b64":
        raw = base64.b64decode(value)
        if len(raw) > MAX_INLINE_PDF_MB * 1024 * 1024:
            raise ValueError(
                f"inline PDF too large ({len(raw) / 1024 / 1024:.1f} MB); "
                f"use pdf_url or volume_path for files > {MAX_INLINE_PDF_MB} MB"
            )
        return raw, "b64"

    if key == "volume_path":
        p = Path(value)
        if not p.is_file():
            raise ValueError(f"volume_path not found inside container: {value}")
        return p.read_bytes(), f"volume:{value}"

    raise ValueError(f"unknown source: {key}")


# -----------------------------------------------------------------------------
# MinerU invocation
# -----------------------------------------------------------------------------

async def _run_mineru(
    pdf_bytes: bytes,
    basename: str,
    work_dir: Path,
    *,
    start_page: int,
    end_page: int | None,
    lang: str,
    backend: str,
    formula_enable: bool,
    table_enable: bool,
) -> Path:
    if not _MINERU_AVAILABLE:
        raise RuntimeError(f"mineru is not importable: {MINERU_VERSION}")
    # Late re-import keeps the static import wrapped; the binding is the real one here.
    from mineru.cli.common import aio_do_parse as _aio_do_parse  # type: ignore[import-not-found]

    await _aio_do_parse(
        output_dir=str(work_dir),
        pdf_file_names=[basename],
        pdf_bytes_list=[pdf_bytes],
        p_lang_list=[lang],
        backend=backend,
        parse_method="auto",
        formula_enable=formula_enable,
        table_enable=table_enable,
        f_dump_md=True,
        f_dump_content_list=True,
        f_dump_middle_json=True,
        start_page_id=start_page,
        end_page_id=end_page,
    )

    candidates = sorted(work_dir.rglob(f"{basename}.md"))
    if not candidates:
        raise RuntimeError(
            f"MinerU did not produce {basename}.md anywhere under {work_dir}"
        )
    return candidates[0].parent


# -----------------------------------------------------------------------------
# Output packaging
# -----------------------------------------------------------------------------

def _package_tarball(output_dir: Path) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for child in sorted(output_dir.iterdir()):
            tar.add(child, arcname=child.name, recursive=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _package_inline(output_dir: Path, basename: str) -> dict[str, Any]:
    md_path = output_dir / f"{basename}.md"
    cl_path = output_dir / f"{basename}_content_list.json"
    if not cl_path.is_file():
        cl_path = output_dir / f"{basename}_content_list_v2.json"
    mid_path = output_dir / f"{basename}_middle.json"

    images: dict[str, str] = {}
    images_dir = output_dir / "images"
    if images_dir.is_dir():
        for img in sorted(images_dir.iterdir()):
            if img.is_file():
                images[img.name] = base64.b64encode(img.read_bytes()).decode("ascii")

    return {
        "markdown": md_path.read_text(encoding="utf-8") if md_path.is_file() else "",
        "content_list": json.loads(cl_path.read_text(encoding="utf-8")) if cl_path.is_file() else [],
        "middle": json.loads(mid_path.read_text(encoding="utf-8")) if mid_path.is_file() else {},
        "images": images,
    }


# -----------------------------------------------------------------------------
# Handler
# -----------------------------------------------------------------------------

def _maybe_progress(job: dict, data: dict) -> None:
    """Best-effort progress update. Tests / sync clients without a job id
    shouldn't fail just because we tried to surface progress."""
    try:
        runpod.serverless.progress_update(job, data)
    except Exception:  # noqa: BLE001
        pass


async def handler(job: dict) -> dict:
    started = time.monotonic()
    try:
        cleaned = _validate_input(job.get("input") or {})

        # rp_validator gives us strict types; translate the -1 sentinel back
        # to None so MinerU treats it as "until end of document".
        end_page_val = cleaned["end_page"]
        end_page = None if end_page_val is None or end_page_val < 0 else int(end_page_val)

        # Surface progress to RunPod's dashboard / streaming consumers.
        _maybe_progress(job, {"phase": "fetching_pdf"})
        pdf_bytes, source = await _resolve_pdf_bytes(cleaned)

        _maybe_progress(job, {
            "phase": "parsing",
            "pdf_bytes": len(pdf_bytes),
            "start_page": cleaned["start_page"],
            "end_page": end_page,
        })

        with tempfile.TemporaryDirectory(prefix="mineru-job-") as tmp:
            work_dir = Path(tmp)
            output_dir = await _run_mineru(
                pdf_bytes,
                basename=cleaned["basename"],
                work_dir=work_dir,
                start_page=cleaned["start_page"],
                end_page=end_page,
                lang=cleaned["lang"],
                backend=cleaned["backend"],
                formula_enable=cleaned["formula_enable"],
                table_enable=cleaned["table_enable"],
            )

            _maybe_progress(job, {"phase": "packaging"})

            pages_processed = (
                (end_page - cleaned["start_page"] + 1) if end_page is not None else -1
            )
            response: dict[str, Any] = {
                "ok": True,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "pages_processed": pages_processed,
                "mineru_version": MINERU_VERSION,
                "source": source,
            }
            if cleaned["return"] == "inline":
                response.update(_package_inline(output_dir, cleaned["basename"]))
            else:
                response["tarball_b64"] = _package_tarball(output_dir)
            return response

    except Exception as exc:  # noqa: BLE001
        # Top-level `error` key tells RunPod to mark this job FAILED.
        # Keep `ok=false` and the structured details so clients see context.
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "ok": False,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "mineru_version": MINERU_VERSION,
            "traceback": traceback.format_exc(limit=5),
        }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
