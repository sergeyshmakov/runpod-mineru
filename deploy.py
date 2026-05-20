"""Create a runpod-mineru serverless endpoint.

Reads RUNPOD_API_KEY from environment or .env. Every endpoint knob is exposed
as a CLI flag so the same script works for any consumer with different
scaling/cost trade-offs.

Quick recipes
-------------
Fast spiky workload (documents arriving sporadically, latency matters):
    python deploy.py --template-id $TID --idle-timeout 10 --workers-min 0 \\
                     --flashboot --gpu-ids AMPERE_24

Steady throughput (always-on indexer):
    python deploy.py --template-id $TID --idle-timeout 5 --workers-min 1 \\
                     --workers-max 10 --gpu-ids AMPERE_24

Long single jobs (full-book parse, OK to wait):
    python deploy.py --template-id $TID --execution-timeout 3600 \\
                     --workers-max 1 --idle-timeout 30
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


DEFAULTS = {
    "name": "mineru-2.5-vlm",
    "gpu_ids": "AMPERE_24",
    "workers_min": 0,
    "workers_max": 3,
    "idle_timeout": 10,
    "execution_timeout": 900,
    "container_disk_gb": 30,
    "flashboot": True,
    "scaler_type": "QUEUE_DELAY",
    "scaler_value": 4,
}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    src = p.add_argument_group("image source (one of)")
    src.add_argument(
        "--image",
        default=os.environ.get("MINERU_IMAGE_REF"),
        help="Docker image reference (creates a template). e.g. docker.io/me/runpod-mineru:0.1",
    )
    src.add_argument(
        "--template-id",
        default=os.environ.get("MINERU_TEMPLATE_ID"),
        help="Existing RunPod template id to attach to (e.g. from RunPod's GitHub auto-build).",
    )

    end = p.add_argument_group("endpoint identity")
    end.add_argument("--name", default=DEFAULTS["name"], help=f"endpoint name (default: {DEFAULTS['name']!r})")

    sc = p.add_argument_group("scaling — what your wallet sees")
    sc.add_argument(
        "--workers-min",
        type=int,
        default=DEFAULTS["workers_min"],
        help=(
            f"minimum always-on workers (default: {DEFAULTS['workers_min']}). "
            f"0 = full scale-to-zero, pay only while processing. "
            f">0 = pay for that many workers 24/7 to eliminate cold starts."
        ),
    )
    sc.add_argument(
        "--workers-max",
        type=int,
        default=DEFAULTS["workers_max"],
        help=f"maximum concurrent workers (default: {DEFAULTS['workers_max']}).",
    )
    sc.add_argument(
        "--idle-timeout",
        type=int,
        default=DEFAULTS["idle_timeout"],
        help=(
            f"seconds a worker stays alive after finishing a job before scale-to-zero "
            f"(default: {DEFAULTS['idle_timeout']}). lower = lower cost, more cold starts."
        ),
    )
    sc.add_argument(
        "--flashboot",
        dest="flashboot",
        action="store_true",
        default=DEFAULTS["flashboot"],
        help="enable RunPod FlashBoot — fast cold start via container snapshotting (default: on).",
    )
    sc.add_argument(
        "--no-flashboot",
        dest="flashboot",
        action="store_false",
        help="disable FlashBoot.",
    )
    sc.add_argument(
        "--scaler-type",
        choices=["QUEUE_DELAY", "REQUEST_COUNT"],
        default=DEFAULTS["scaler_type"],
        help=(
            "autoscaler trigger. QUEUE_DELAY = scale up when jobs wait > scaler-value seconds. "
            "REQUEST_COUNT = scale up when active requests/worker > scaler-value."
        ),
    )
    sc.add_argument(
        "--scaler-value",
        type=int,
        default=DEFAULTS["scaler_value"],
        help=f"threshold for --scaler-type (default: {DEFAULTS['scaler_value']}).",
    )

    hw = p.add_argument_group("hardware")
    hw.add_argument(
        "--gpu-ids",
        default=DEFAULTS["gpu_ids"],
        help=(
            f"RunPod GPU pool (default: {DEFAULTS['gpu_ids']}). "
            f"common options: AMPERE_24, ADA_24, AMPERE_48, AMPERE_80, ADA_80_PRO. "
            f"avoid ADA_48_PRO until xformers ships a Blackwell kernel."
        ),
    )
    hw.add_argument(
        "--container-disk-gb",
        type=int,
        default=DEFAULTS["container_disk_gb"],
        help=(
            f"per-worker container disk (default: {DEFAULTS['container_disk_gb']} GB). "
            f"Image bakes ~4 GB of model weights (VLM + pipeline OCR), so the worker "
            f"image is large; bump if your local cache or temp PDFs push over 30 GB."
        ),
    )

    job = p.add_argument_group("job limits")
    job.add_argument(
        "--execution-timeout",
        type=int,
        default=DEFAULTS["execution_timeout"],
        help=(
            f"per-job hard timeout in seconds (default: {DEFAULTS['execution_timeout']}). "
            f"RunPod terminates the worker if a single job exceeds this. "
            f"~5 s/page on AMPERE_24 → 900 s covers ~180 pages comfortably."
        ),
    )

    return p


def main() -> int:
    args = _build_parser().parse_args()

    runpod.api_key = os.environ.get("RUNPOD_API_KEY")
    if not runpod.api_key:
        print("RUNPOD_API_KEY is not set (env or .env).", file=sys.stderr)
        return 2

    if not args.image and not args.template_id:
        print(
            "Provide --image <ref> (to create a template) or --template-id <id> "
            "(to reuse an existing one).",
            file=sys.stderr,
        )
        return 2
    if args.image and args.template_id:
        print("--image and --template-id are mutually exclusive.", file=sys.stderr)
        return 2

    template_id = args.template_id
    if args.image:
        print(f"Creating template for image {args.image} …")
        template = runpod.create_template(
            name=f"{args.name}-tpl",
            image_name=args.image,
            is_serverless=True,
            container_disk_in_gb=args.container_disk_gb,
        )
        template_id = template["id"]
        print(f"  template id: {template_id}")

    print(f"Creating endpoint '{args.name}' on {args.gpu_ids} …")
    endpoint = runpod.create_endpoint(
        name=args.name,
        template_id=template_id,
        gpu_ids=args.gpu_ids,
        workers_min=args.workers_min,
        workers_max=args.workers_max,
        idle_timeout=args.idle_timeout,
        execution_timeout_ms=args.execution_timeout * 1000,
        flashboot=args.flashboot,
        scaler_type=args.scaler_type,
        scaler_value=args.scaler_value,
    )
    endpoint_id = endpoint["id"]

    print()
    print("Endpoint created:")
    print(f"  id:                {endpoint_id}")
    print(f"  name:              {args.name}")
    print(f"  gpu:               {args.gpu_ids}")
    print(f"  workers:           {args.workers_min} … {args.workers_max}")
    print(f"  idle timeout:      {args.idle_timeout}s")
    print(f"  execution timeout: {args.execution_timeout}s")
    print(f"  flashboot:         {args.flashboot}")
    print(f"  scaler:            {args.scaler_type} @ {args.scaler_value}")
    print(f"  container disk:    {args.container_disk_gb} GB")
    print()
    print("Save to .env:")
    print(f"  RUNPOD_ENDPOINT_ID={endpoint_id}")
    if args.image and template_id:
        print(f"  MINERU_TEMPLATE_ID={template_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
