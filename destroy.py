"""Tear down a mineru-runpod endpoint and (optionally) its template.

Reads RUNPOD_ENDPOINT_ID + MINERU_TEMPLATE_ID from environment / .env, or
takes them on the CLI.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import runpod


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint-id",
        default=os.environ.get("RUNPOD_ENDPOINT_ID"),
    )
    parser.add_argument(
        "--template-id",
        default=os.environ.get("MINERU_TEMPLATE_ID"),
    )
    parser.add_argument(
        "--keep-template",
        action="store_true",
        help="Only delete the endpoint; leave the template registered.",
    )
    args = parser.parse_args()

    runpod.api_key = os.environ.get("RUNPOD_API_KEY")
    if not runpod.api_key:
        print("RUNPOD_API_KEY is not set.", file=sys.stderr)
        return 2

    if args.endpoint_id:
        # The Python SDK doesn't expose delete_endpoint directly across versions —
        # update workers to 0 first, then call the raw GraphQL helper if present.
        print(f"Scaling endpoint {args.endpoint_id} to 0 workers and deleting …")
        try:
            runpod.update_endpoint_template  # smoke check
        except AttributeError:
            print(
                "  runpod SDK is too old; please run `pip install -U runpod`.",
                file=sys.stderr,
            )
            return 2
        # Best-effort delete; SDK API surface here changes between versions.
        delete_fn = getattr(runpod, "delete_endpoint", None) or getattr(
            runpod.api, "delete_endpoint", None
        )
        if delete_fn is None:
            print(
                "  no delete_endpoint helper in this SDK; delete via dashboard "
                "or RunPod GraphQL `deleteEndpoint(input: { id: ... })`.",
                file=sys.stderr,
            )
        else:
            delete_fn(args.endpoint_id)
            print(f"  endpoint {args.endpoint_id} deleted")

    if args.template_id and not args.keep_template:
        print(f"Deleting template {args.template_id} …")
        delete_fn = getattr(runpod, "delete_template", None) or getattr(
            runpod.api, "delete_template", None
        )
        if delete_fn is None:
            print(
                "  no delete_template helper in this SDK; delete via dashboard.",
                file=sys.stderr,
            )
        else:
            delete_fn(args.template_id)
            print(f"  template {args.template_id} deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
