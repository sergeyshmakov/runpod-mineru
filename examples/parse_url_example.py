"""Minimal example: parse a publicly hosted PDF via the deployed endpoint.

Usage:
    set RUNPOD_API_KEY=...
    set RUNPOD_ENDPOINT_ID=...
    python examples/parse_url_example.py https://example.com/report.pdf
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mineru_client import MineruClient


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: parse_url_example.py <pdf_url>", file=sys.stderr)
        return 2
    url = sys.argv[1]

    client = MineruClient(
        endpoint_id=os.environ["RUNPOD_ENDPOINT_ID"],
        api_key=os.environ["RUNPOD_API_KEY"],
    )
    result = client.parse_pdf(
        pdf_url=url,
        start_page=0,
        end_page=4,            # first 5 pages, for a quick smoke test
        return_format="tarball_b64",
        basename="example",
    )
    print(
        f"ok={result['ok']}  "
        f"elapsed={result['elapsed_seconds']}s  "
        f"version={result['mineru_version']}"
    )
    dest = Path("./out/parse_url_example")
    client.save_tarball(result, dest)
    print(f"Extracted to: {dest.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
