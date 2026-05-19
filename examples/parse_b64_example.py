"""Minimal example: parse a local PDF by sending it inline as base64.

Only practical for documents ≤ ~10 MB on /run and ~20 MB on /runsync —
RunPod's gateway rejects bigger payloads. For larger files, use a URL or
a mounted volume_path.

Usage:
    set RUNPOD_API_KEY=...
    set RUNPOD_ENDPOINT_ID=...
    python examples/parse_b64_example.py path/to/small_doc.pdf
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mineru_client import MineruClient


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: parse_b64_example.py <pdf_path>", file=sys.stderr)
        return 2
    pdf_path = Path(sys.argv[1])
    if not pdf_path.is_file():
        print(f"file not found: {pdf_path}", file=sys.stderr)
        return 2

    client = MineruClient(
        endpoint_id=os.environ["RUNPOD_ENDPOINT_ID"],
        api_key=os.environ["RUNPOD_API_KEY"],
    )
    result = MineruClient.parse_pdf_from_file(
        client,
        pdf_path,
        return_format="inline",   # small enough to keep everything in-memory
        basename=pdf_path.stem,
    )
    print(
        f"ok={result['ok']}  "
        f"elapsed={result['elapsed_seconds']}s  "
        f"version={result['mineru_version']}  "
        f"images={len(result.get('images') or {})}"
    )
    dest = Path(f"./out/{pdf_path.stem}")
    client.save_inline(result, dest, basename=pdf_path.stem)
    print(f"Saved to: {dest.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
