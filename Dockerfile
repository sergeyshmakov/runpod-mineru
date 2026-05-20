# MinerU on RunPod Serverless — generic PDF parsing worker.
# MinerU 3.1.x runtime, MinerU2.5-Pro-2604-1.2B VLM as the default model.
#
# Base image: vllm/vllm-openai (recommended by MinerU upstream — bundles CUDA
# + a working vLLM that the VLM backend depends on).
#
# At runtime: handler.py listens for RunPod jobs, downloads/decodes the input
# PDF, calls MinerU's async parse, and returns the result as a base64 tarball.
#
# Model weights live on RunPod's per-endpoint Cached Models volume mounted
# under /runpod-volume/huggingface-cache (matches the path RunPod's tutorial
# at docs.runpod.io/tutorials/serverless/model-caching-text uses). Snapshot
# layout is the HuggingFace standard:
#   /runpod-volume/huggingface-cache/hub/models--{org}--{name}/snapshots/...
#
# To use this template effectively:
#   1. In the RunPod endpoint dashboard, enable "Cached Models"
#   2. Add `opendatalab/MinerU2.5-Pro-2604-1.2B` for the VLM backend
#   3. (Optional) Add pipeline models if you use the `pipeline` backend
#
# First cold start populates the cache (non-billable); subsequent starts
# read weights directly from the volume. Image stays ~2.5 GB smaller than
# the previous bake-in approach.

ARG VLLM_VERSION=v0.11.2
FROM vllm/vllm-openai:${VLLM_VERSION}

# HF_HOME points at the RunPod volume so HuggingFace + MinerU resolve cached
# weights without redownloading.
#
# HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 force the HuggingFace libs to
# read from cache only. Per RunPod's model-caching tutorial: when Cached
# Models is enabled, the volume is populated BEFORE the worker starts
# (non-billable), so the model is always already there by the time the
# handler runs. Forcing offline mode prevents the failure case where a
# misconfigured endpoint silently re-downloads at job time on every fresh
# worker (which IS billable). Users get a clean "cache miss" error instead
# of mysterious billing — fail fast > fail slow.
#
# Model selection: MinerU 3.1.x's library default is already
# `opendatalab/MinerU2.5-Pro-2604-1.2B` for the VLM backend — no env var
# override needed. (Earlier versions used 2509 and required gymnastics to
# override; we just upgraded out of that problem.)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/runpod-volume/huggingface-cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# vllm-openai inherits an entrypoint that launches the OpenAI server. Override
# it so our handler can be the process.
ENTRYPOINT []

# System deps. The base image already has CUDA + Python; we only need the
# things mineru/pdf processing want at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        poppler-utils \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /worker

# Install uv (10x+ faster than pip on resolution-heavy installs like
# mineru[core,vllm], which churns through pydantic / opencv / numpy
# version conflicts with the base image). Negligible image size (~10 MB)
# in exchange for a meaningful build-time win.
RUN pip install --no-cache-dir uv

# Install MinerU + RunPod worker SDK. mineru[core,vllm] pulls the VLM-engine
# dependencies that match the vllm version in the base image.
COPY requirements.txt /worker/requirements.txt
RUN uv pip install --system --no-cache -r requirements.txt

# Model weights are NOT baked into the image. They come from RunPod's
# Cached Models volume at /runpod-volume/huggingface-cache (configured per
# endpoint in the dashboard). First cold start populates the cache from
# HuggingFace (non-billable); subsequent starts read straight off the volume.

# Copy the worker code last so iterating on it doesn't bust the pip layer.
COPY handler.py /worker/handler.py

# Tiny fixture PDF used by the RunPod Hub validation tests (.runpod/tests.json
# references /worker/test-fixture.pdf). Tiny (<1 KB) so it adds nothing to the
# image and gives Hub a real document to round-trip on submission.
COPY .runpod/test-fixture.pdf /worker/test-fixture.pdf

# RunPod's serverless runtime invokes Python directly. `python3` is what
# vllm/vllm-openai ships on PATH; `python` is not always aliased.
CMD ["python3", "-u", "handler.py"]
