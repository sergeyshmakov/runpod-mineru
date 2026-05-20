"""RunPod serverless worker for MinerU document parsing.

Generic — knows nothing about any particular calling project. Accepts a document
from one of three transports (URL / inline base64 / mounted-volume path),
parses with MinerU's chosen backend, and returns the output either as a
base64-encoded tarball, inline, or as a presigned URL to an S3-compatible bucket.

Runtime: MinerU 3.1.x library, default model `opendatalab/MinerU2.5-Pro-2604-1.2B`.

Input formats (auto-detected from bytes):
    PDF   — `application/pdf`
    Image — PNG, JPEG, GIF, BMP, TIFF, WebP (single-page conversion to PDF)
    DOCX  — Microsoft Word
    PPTX  — Microsoft PowerPoint
    XLSX  — Microsoft Excel

Backends (per MinerU 3.1.x official docs):
    pipeline           — PaddleOCR + layout/formula/table models. 109-language OCR.
                          Best for non-Latin scripts; respects `lang` parameter.
    vlm-auto-engine    — Single end-to-end VLM via vLLM (default). Fast on EN/CH.
                          Ignores `lang`; native layout preservation.
    vlm-http-client    — Same VLM, but served by an external vLLM server (set
                          `server_url`). Useful for splitting model-serving from
                          the worker pool.
    hybrid-auto-engine — Mix of pipeline + VLM, auto-routed based on page content. Best
                          quality on mixed-content docs; largest VRAM footprint.
    hybrid-http-client — Hybrid with external VLM server.

API contract (job input)
------------------------
Exactly one of:
    file_url     : str           — public or presigned HTTP(S) URL
    file_b64     : str           — base64-encoded file bytes (≤ 20 MB; RunPod gateway cap)
    volume_path  : str           — absolute path to a file inside the container
                                    (a mounted RunPod volume, or a file baked into the image)

Optional:
    start_page    : int = 0      — 0-based, inclusive (PDF only)
    end_page      : int          — 0-based, inclusive; omit / -1 = end of document
    lang          : str = "en"   — language hint passed to MinerU (pipeline backend
                                    only; VLM backends ignore it). Script-family
                                    codes: `east_slavic` (Russian/Ukrainian),
                                    `cyrillic`, `latin`, `arabic`, `devanagari`,
                                    `japan`, `korean`, etc. NOT ISO codes.
    backend       : str          — MinerU backend, default "vlm-auto-engine"
    server_url    : str          — Required for `*-http-client` backends.
                                    URL of an external vLLM OpenAI-compatible server.
    formula_enable: bool = True
    table_enable  : bool = True
    return        : str          — "tarball_b64" (default) | "inline" | "s3"
                                    "s3" uploads the .tar.gz output to the bucket
                                    configured via BUCKET_* env vars and returns
                                    a presigned URL valid for 1 hour. Use this
                                    when outputs would exceed RunPod's gateway
                                    response cap (~20 MB).
    basename      : str = "doc"  — filename stem for output files

Response on success
-------------------
    {
      "ok": true,
      "elapsed_seconds": 18.4,
      "pages_processed": 100,
      "mineru_version": "3.1.x",
      "source": "url:https://...",
      "debug": {
          "backend": "vlm-auto-engine",
          "input_format": "pdf",
          "model_dir": "/runpod-volume/.../snapshots/<hash>",
          "gpu": {"name": "NVIDIA RTX 4090", "compute_capability": "8.9", "total_memory_gb": 23.99},
          "phase_ms": {"fetch_input": 12, "mineru_parse": 18420, "package": 95}
      },
      "tarball_b64": "..."         // or markdown/content_list/middle/images for inline,
                                    // or `tarball_url` + `tarball_url_expires_at` for s3
    }

Response on failure (RunPod marks job FAILED via the top-level `error` key)
--------------------------------------------------------------------------
    {
      "error": "ValueError: must provide exactly one of file_url / file_b64 / volume_path",
      "ok": false,
      "elapsed_seconds": 0.1,
      "mineru_version": "3.1.x",
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


def _collect_gpu_info() -> dict[str, Any]:
    """Best-effort GPU inventory for the response's `debug` block.

    Helps callers distinguish a 4090 from an A5000 from a Blackwell MIG slice
    without having to read worker logs. compute_capability >= 12.0 is what
    triggers the xformers flash-attn crash on the VLM backend.
    """
    try:
        import torch  # noqa: PLC0415
        if not torch.cuda.is_available():
            return {"available": False}
        props = torch.cuda.get_device_properties(0)
        return {
            "available": True,
            "name": props.name,
            "compute_capability": f"{props.major}.{props.minor}",
            "total_memory_gb": round(props.total_memory / 1024**3, 2),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def _find_model_dir() -> str | None:
    """Locate the MinerU model snapshot under HF_HOME so we can prove which
    weights actually loaded (Pro-2604 vs the library default 2509)."""
    hf_home = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    hub = Path(hf_home) / "hub"
    if not hub.is_dir():
        return None
    matches = list(hub.glob("models--opendatalab--MinerU*"))
    if not matches:
        return None
    # If multiple MinerU model dirs are cached, report the most recently used
    # one — that's the one the library most likely resolved to.
    best = max(matches, key=lambda p: p.stat().st_mtime)
    snapshots = best / "snapshots"
    if snapshots.is_dir():
        snap_dirs = [d for d in snapshots.iterdir() if d.is_dir()]
        if snap_dirs:
            return str(max(snap_dirs, key=lambda p: p.stat().st_mtime))
    return str(best)


def _resolve_snapshot_path(hub_root: Path, model_id: str) -> dict[str, Any]:
    """Emulate the resolve_snapshot_path() helper from RunPod's tutorial.

    Returns a dict that says what the tutorial's algorithm would have found
    for `model_id` at `hub_root` — including whether refs/main is stale
    (points at a hash that doesn't exist in snapshots/).
    """
    out: dict[str, Any] = {
        "model_id": model_id,
        "expected_root": "",
        "model_root_exists": False,
        "refs_main_path": "",
        "refs_main_content": None,
        "snapshots_dir_exists": False,
        "snapshot_subdirs": [],
        "resolved_path": None,
        "resolution_method": None,
        "issue": None,
    }
    if "/" not in model_id:
        out["issue"] = f"model_id {model_id!r} not in org/name format"
        return out
    org, name = model_id.split("/", 1)
    model_root = hub_root / f"models--{org}--{name}"
    out["expected_root"] = str(model_root)
    if not model_root.is_dir():
        out["issue"] = "model_root not present (RunPod didn't populate, or wrong casing)"
        return out
    out["model_root_exists"] = True

    refs_main = model_root / "refs" / "main"
    out["refs_main_path"] = str(refs_main)
    if refs_main.is_file():
        try:
            out["refs_main_content"] = refs_main.read_text(encoding="utf-8").strip()
        except OSError as e:
            out["refs_main_content"] = f"<read error: {e}>"

    snapshots_dir = model_root / "snapshots"
    out["snapshots_dir_exists"] = snapshots_dir.is_dir()
    if out["snapshots_dir_exists"]:
        try:
            out["snapshot_subdirs"] = sorted(
                d.name for d in snapshots_dir.iterdir() if d.is_dir()
            )
        except OSError as e:
            out["issue"] = f"snapshots/ iter error: {e}"
            return out

    # Resolution attempt 1: refs/main → snapshots/<hash>/
    if out["refs_main_content"] and isinstance(out["refs_main_content"], str):
        candidate = snapshots_dir / out["refs_main_content"]
        if candidate.is_dir():
            out["resolved_path"] = str(candidate)
            out["resolution_method"] = "refs/main"
            return out
        out["issue"] = (
            f"refs/main points at {out['refs_main_content']!r} but "
            f"snapshots/{out['refs_main_content']}/ does not exist (stale refs/main)"
        )

    # Resolution attempt 2: first available snapshot subdir
    if out["snapshot_subdirs"]:
        first = snapshots_dir / out["snapshot_subdirs"][0]
        out["resolved_path"] = str(first)
        out["resolution_method"] = "first snapshot subdir (fallback)"
        return out

    if out["issue"] is None:
        out["issue"] = "no snapshots/ subdir or no entries inside it"
    return out


def _probe_filesystem() -> dict[str, Any]:
    """Inspect /runpod-volume layout for Cached Models debugging.

    Returns whatever's actually on disk where MinerU's HF lookup expects it.
    Triggered by `probe: true` in the input. Used to diagnose
    LocalEntryNotFoundError on workers that have Cached Models configured but
    aren't finding the model.

    Safe to call without MinerU installed. Read-only. No network. No PDF.
    """
    def _list(p: Path, max_entries: int = 50) -> list[str] | str:
        try:
            entries = sorted(p.iterdir())
        except (PermissionError, FileNotFoundError) as e:
            return f"<error: {type(e).__name__}: {e}>"
        result: list[str] = []
        for entry in entries[:max_entries]:
            kind = "d" if entry.is_dir() else "f"
            try:
                size = entry.stat().st_size if entry.is_file() else "-"
            except OSError:
                size = "?"
            result.append(f"{kind} {entry.name} {size}")
        if len(entries) > max_entries:
            result.append(f"... ({len(entries) - max_entries} more entries elided)")
        return result

    hf_home = os.environ.get("HF_HOME", "")
    hub_path = Path(hf_home) / "hub" if hf_home else None

    out: dict[str, Any] = {
        "env": {
            "HF_HOME": hf_home,
            "HF_HUB_CACHE": os.environ.get("HF_HUB_CACHE", ""),
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE", ""),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE", ""),
            "TRANSFORMERS_CACHE": os.environ.get("TRANSFORMERS_CACHE", ""),
            "MINERU_MODEL_SOURCE": os.environ.get("MINERU_MODEL_SOURCE", ""),
            "MINERU_VL_MODEL_NAME": os.environ.get("MINERU_VL_MODEL_NAME", ""),
        },
        "paths": {},
        "models_found": [],
        "resolution_attempts": [],
    }

    # Try the tutorial's snapshot resolver for each model MinerU would care
    # about. Reports whether refs/main is stale, whether canonical casing is
    # present, and what (if anything) MinerU's library would find.
    if hub_path and hub_path.is_dir():
        for model_id in (
            "opendatalab/MinerU2.5-Pro-2604-1.2B",  # VLM backend
            "opendatalab/PDF-Extract-Kit-1.0",      # pipeline backend
        ):
            out["resolution_attempts"].append(
                _resolve_snapshot_path(hub_path, model_id)
            )

    for label, path_str in (
        ("/runpod-volume", "/runpod-volume"),
        ("/runpod-volume/huggingface-cache", "/runpod-volume/huggingface-cache"),
        ("/runpod-volume/huggingface-cache/hub", "/runpod-volume/huggingface-cache/hub"),
        ("HF_HOME", hf_home),
        ("HF_HOME/hub", str(hub_path) if hub_path else ""),
    ):
        if not path_str:
            out["paths"][label] = "<empty path>"
            continue
        p = Path(path_str)
        if not p.exists():
            out["paths"][label] = "<not present>"
            continue
        if not p.is_dir():
            out["paths"][label] = "<not a directory>"
            continue
        out["paths"][label] = _list(p)

    # Hunt for any `models--*` directories regardless of casing, anywhere
    # under /runpod-volume up to depth 4. This catches the case where
    # RunPod populated under a different path than HF_HOME/hub.
    for search_root in ("/runpod-volume",):
        root = Path(search_root)
        if not root.is_dir():
            continue
        try:
            for path in root.rglob("models--*"):
                # Stop if we go deeper than 4 levels
                try:
                    rel_depth = len(path.relative_to(root).parts)
                except ValueError:
                    continue
                if rel_depth > 4:
                    continue
                snapshots = path / "snapshots"
                snap_names: list[str] = []
                if snapshots.is_dir():
                    try:
                        snap_names = [d.name for d in snapshots.iterdir() if d.is_dir()][:5]
                    except OSError:
                        pass
                out["models_found"].append({
                    "path": str(path),
                    "depth": rel_depth,
                    "snapshots": snap_names,
                })
                if len(out["models_found"]) >= 20:
                    break
        except (PermissionError, OSError) as e:
            out["models_found_error"] = f"{type(e).__name__}: {e}"

    return out


# RunPod's gateway caps payloads at 10 MB (/run) and 20 MB (/runsync). The
# 20 MB ceiling is the largest a caller can realistically send inline; the
# handler enforces it defensively but oversized requests are normally
# rejected at the gateway before reaching us. For larger files, use
# file_url or volume_path.
MAX_INLINE_FILE_MB = 20

# Magic bytes for the input formats MinerU 3.1.x supports.
# - PDFs and Office docs pass straight to aio_do_parse (it auto-detects).
# - Images need preprocessing to single-page PDF via images_bytes_to_pdf_bytes.
_IMAGE_MAGIC = (
    b"\x89PNG\r\n\x1a\n",   # PNG
    b"\xff\xd8\xff",        # JPEG
    b"GIF87a", b"GIF89a",   # GIF
    b"BM",                  # BMP
    b"II*\x00",             # TIFF little-endian
    b"MM\x00*",             # TIFF big-endian
    b"RIFF",                # WebP container (also AVI / WAV — rare as PDF inputs)
)
_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK\x03\x04"  # DOCX / PPTX / XLSX (all OOXML) and ZIP itself


def _detect_format(file_bytes: bytes) -> str:
    """Return one of: "pdf" | "image" | "ooxml" | "unknown".

    OOXML (DOCX/PPTX/XLSX) all start with the ZIP magic; MinerU's own
    `guess_suffix_by_bytes` inspects the archive's content-types to discriminate.
    We just flag "ooxml" and let MinerU decide which of the three it is.
    """
    if not file_bytes:
        return "unknown"
    if file_bytes.startswith(_PDF_MAGIC):
        return "pdf"
    if any(file_bytes.startswith(m) for m in _IMAGE_MAGIC):
        return "image"
    if file_bytes.startswith(_ZIP_MAGIC):
        return "ooxml"
    return "unknown"


# -----------------------------------------------------------------------------
# Input schema (rp_validator) — type coercion + bounds for the easy fields.
# The "exactly one of file_url/file_b64/volume_path" rule is enforced manually
# below because rp_validator doesn't express XOR.
# -----------------------------------------------------------------------------

INPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "file_url":       {"type": str,  "required": False, "default": None},
    "file_b64":       {"type": str,  "required": False, "default": None},
    "volume_path":    {"type": str,  "required": False, "default": None},
    # When `probe` is true the handler skips MinerU entirely and returns a
    # filesystem dump of /runpod-volume + relevant env vars. Used to debug
    # RunPod Cached Models setup.
    "probe":          {"type": bool, "required": False, "default": False},
    "start_page":     {"type": int,  "required": False, "default": 0,
                       "constraints": lambda x: x >= 0},
    "end_page":       {"type": int,  "required": False, "default": -1},
    "lang":           {"type": str,  "required": False, "default": "en"},
    "backend":        {"type": str,  "required": False, "default": "vlm-auto-engine"},
    "server_url":     {"type": str,  "required": False, "default": None},
    "formula_enable": {"type": bool, "required": False, "default": True},
    "table_enable":   {"type": bool, "required": False, "default": True},
    "return":         {"type": str,  "required": False, "default": "tarball_b64",
                       "constraints": lambda x: x in {"tarball_b64", "inline", "s3"}},
    "basename":       {"type": str,  "required": False, "default": "doc",
                       "constraints": lambda x: bool(x) and all(
                           c.isalnum() or c in "-_" for c in x)},
}


_VALID_RETURNS = {"tarball_b64", "inline", "s3"}


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

    sources = [k for k in ("file_url", "file_b64", "volume_path") if cleaned.get(k)]
    if len(sources) != 1:
        raise ValueError(
            f"must provide exactly one of file_url / file_b64 / volume_path "
            f"(got {sources!r})"
        )
    return cleaned


# -----------------------------------------------------------------------------
# Input → PDF bytes
# -----------------------------------------------------------------------------

async def _resolve_input_bytes(job_input: dict) -> tuple[bytes, str]:
    """Return (file_bytes, source_label). Raises ValueError on bad input.

    Format is auto-detected downstream by `_detect_format` / MinerU itself —
    this function just fetches the raw bytes from whichever transport the
    caller used.
    """
    sources = {
        "file_url": job_input.get("file_url"),
        "file_b64": job_input.get("file_b64"),
        "volume_path": job_input.get("volume_path"),
    }
    provided = [k for k, v in sources.items() if v]
    if len(provided) != 1:
        raise ValueError(
            f"must provide exactly one of file_url / file_b64 / volume_path "
            f"(got {provided!r})"
        )
    key = provided[0]
    value = sources[key]

    if key == "file_url":
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(value, follow_redirects=True)
            resp.raise_for_status()
            return resp.content, f"url:{value}"

    if key == "file_b64":
        raw = base64.b64decode(value)
        if len(raw) > MAX_INLINE_FILE_MB * 1024 * 1024:
            raise ValueError(
                f"inline file too large ({len(raw) / 1024 / 1024:.1f} MB); "
                f"use file_url or volume_path for files > {MAX_INLINE_FILE_MB} MB"
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
    file_bytes: bytes,
    basename: str,
    work_dir: Path,
    *,
    input_format: str,
    start_page: int,
    end_page: int | None,
    lang: str,
    backend: str,
    server_url: str | None,
    formula_enable: bool,
    table_enable: bool,
) -> Path:
    if not _MINERU_AVAILABLE:
        raise RuntimeError(f"mineru is not importable: {MINERU_VERSION}")
    # Late re-import keeps the static import wrapped; the binding is the real one here.
    from mineru.cli.common import aio_do_parse as _aio_do_parse  # type: ignore[import-not-found]

    # MinerU's `aio_do_parse` accepts PDFs, DOCX, PPTX, XLSX bytes directly via
    # `pdf_bytes_list` (the name is legacy — it's polymorphic). Images need
    # pre-conversion to single-page PDF first.
    if input_format == "image":
        from mineru.utils.pdf_image_tools import images_bytes_to_pdf_bytes  # type: ignore[import-not-found]  # noqa: PLC0415
        file_bytes = images_bytes_to_pdf_bytes(file_bytes)

    # MinerU 3.1.x adds f_dump_model_output / f_dump_orig_pdf with default True
    # — both write extra artefacts (raw model output JSON, copy of input PDF)
    # that bloat the response tarball without serving callers we know about.
    # Turn them off; callers who want them can fork the handler.
    await _aio_do_parse(
        output_dir=str(work_dir),
        pdf_file_names=[basename],
        pdf_bytes_list=[file_bytes],
        p_lang_list=[lang],
        backend=backend,
        server_url=server_url,
        parse_method="auto",
        formula_enable=formula_enable,
        table_enable=table_enable,
        f_dump_md=True,
        f_dump_content_list=True,
        f_dump_middle_json=True,
        f_dump_model_output=False,
        f_dump_orig_pdf=False,
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


def _build_tarball_bytes(output_dir: Path) -> bytes:
    """Same archive as _package_tarball produces, but as raw bytes (for S3)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for child in sorted(output_dir.iterdir()):
            tar.add(child, arcname=child.name, recursive=True)
    return buf.getvalue()


# Default presigned URL lifetime for `return: "s3"` uploads.
# An hour is enough for a caller to fetch the tarball but short enough that a
# leaked URL stops working before it's interesting.
_S3_PRESIGN_TTL_SECONDS = 3600


def _package_s3(output_dir: Path, basename: str) -> dict[str, Any]:
    """Upload the output tarball to an S3-compatible bucket and return a
    presigned GET URL.

    Required worker env vars: BUCKET_ENDPOINT_URL, BUCKET_NAME,
    BUCKET_ACCESS_KEY_ID, BUCKET_SECRET_ACCESS_KEY. Optional:
    BUCKET_REGION (some providers need this; default empty), BUCKET_PREFIX
    (key path prefix inside the bucket; default empty).
    """
    endpoint = os.environ.get("BUCKET_ENDPOINT_URL", "").strip()
    bucket = os.environ.get("BUCKET_NAME", "").strip()
    access_key = os.environ.get("BUCKET_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("BUCKET_SECRET_ACCESS_KEY", "").strip()
    missing = [
        name for name, val in (
            ("BUCKET_ENDPOINT_URL", endpoint),
            ("BUCKET_NAME", bucket),
            ("BUCKET_ACCESS_KEY_ID", access_key),
            ("BUCKET_SECRET_ACCESS_KEY", secret_key),
        ) if not val
    ]
    if missing:
        raise ValueError(
            f"return='s3' requires worker env vars: {', '.join(missing)}. "
            f"Set these in the RunPod endpoint env config and redeploy."
        )

    region = os.environ.get("BUCKET_REGION", "").strip() or None
    prefix = os.environ.get("BUCKET_PREFIX", "").strip().lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    # boto3 import is lazy so workers that never call return='s3' don't pay
    # the ~50 MB cold-import cost.
    import boto3  # noqa: PLC0415
    from botocore.client import Config  # noqa: PLC0415

    tarball_bytes = _build_tarball_bytes(output_dir)
    # Use a UUID so concurrent jobs with the same basename don't collide.
    import uuid  # noqa: PLC0415
    key = f"{prefix}{basename}-{uuid.uuid4().hex}.tar.gz"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        # SigV4 is required by most S3-compatible providers (R2, B2, MinIO).
        config=Config(signature_version="s3v4"),
    )
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=tarball_bytes,
        ContentType="application/gzip",
    )
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=_S3_PRESIGN_TTL_SECONDS,
    )
    return {
        "tarball_url": url,
        "tarball_url_expires_in": _S3_PRESIGN_TTL_SECONDS,
        "bucket_key": key,
        "bucket_bytes": len(tarball_bytes),
    }


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
    phase_ms: dict[str, int] = {}
    gpu_info = _collect_gpu_info()
    try:
        # Probe mode: bypass MinerU entirely and dump filesystem layout so
        # we can debug Cached Models setup. Bypass input validation since
        # a probe request has no file source.
        raw_input = job.get("input") or {}
        if raw_input.get("probe") is True:
            print("[mineru-worker] probe job: dumping filesystem layout", flush=True)
            probe_data = _probe_filesystem()
            return {
                "ok": True,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "mineru_version": MINERU_VERSION,
                "probe": probe_data,
                "debug": {
                    "gpu": gpu_info,
                    "model_dir": _find_model_dir(),
                    "phase_ms": phase_ms,
                },
            }

        cleaned = _validate_input(raw_input)

        # rp_validator gives us strict types; translate the -1 sentinel back
        # to None so MinerU treats it as "until end of document".
        end_page_val = cleaned["end_page"]
        end_page = None if end_page_val is None or end_page_val < 0 else int(end_page_val)

        backend = cleaned["backend"]
        server_url = cleaned.get("server_url")
        if backend.endswith("-http-client") and not server_url:
            raise ValueError(
                f"backend={backend!r} requires `server_url` pointing at an "
                f"external vLLM OpenAI-compatible server"
            )
        print(
            f"[mineru-worker] starting job: backend={backend} lang={cleaned['lang']} "
            f"start={cleaned['start_page']} end={end_page} "
            f"gpu={gpu_info.get('name', '?')} cc={gpu_info.get('compute_capability', '?')}",
            flush=True,
        )

        # Surface progress to RunPod's dashboard / streaming consumers.
        _maybe_progress(job, {"phase": "fetching_input"})
        t = time.monotonic()
        file_bytes, source = await _resolve_input_bytes(cleaned)
        phase_ms["fetch_input"] = int((time.monotonic() - t) * 1000)

        input_format = _detect_format(file_bytes)
        if input_format == "unknown":
            raise ValueError(
                "input bytes do not match any supported format "
                "(PDF, PNG/JPEG/GIF/BMP/TIFF/WebP image, or DOCX/PPTX/XLSX). "
                "Check that file_b64 was base64-encoded correctly and that "
                "file_url returned the file body (not an error page)."
            )

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
            output_dir = await _run_mineru(
                file_bytes,
                basename=cleaned["basename"],
                work_dir=work_dir,
                input_format=input_format,
                start_page=cleaned["start_page"],
                end_page=end_page,
                lang=cleaned["lang"],
                backend=backend,
                server_url=server_url,
                formula_enable=cleaned["formula_enable"],
                table_enable=cleaned["table_enable"],
            )
            phase_ms["mineru_parse"] = int((time.monotonic() - t) * 1000)

            _maybe_progress(job, {"phase": "packaging"})

            t = time.monotonic()
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
            elif cleaned["return"] == "s3":
                response.update(_package_s3(output_dir, cleaned["basename"]))
            else:
                response["tarball_b64"] = _package_tarball(output_dir)
            phase_ms["package"] = int((time.monotonic() - t) * 1000)

            model_dir = _find_model_dir()
            response["debug"] = {
                "backend": backend,
                "input_format": input_format,
                "model_dir": model_dir,
                "gpu": gpu_info,
                "phase_ms": phase_ms,
            }
            print(
                f"[mineru-worker] done: elapsed={response['elapsed_seconds']}s "
                f"phase_ms={phase_ms} model_dir={model_dir}",
                flush=True,
            )
            return response

    except Exception as exc:  # noqa: BLE001
        # Top-level `error` key tells RunPod to mark this job FAILED.
        # Keep `ok=false` and the structured details so clients see context.
        print(f"[mineru-worker] failed: {type(exc).__name__}: {exc}", flush=True)
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "ok": False,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "mineru_version": MINERU_VERSION,
            "traceback": traceback.format_exc(limit=5),
            "debug": {
                "gpu": gpu_info,
                "model_dir": _find_model_dir(),
                "phase_ms": phase_ms,
            },
        }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
