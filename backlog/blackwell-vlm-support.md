# Backlog: Blackwell GPU support for the VLM backend

**Status**: Blocked on MinerU upstream
**Last verified**: 2026-05-27 against MinerU 3.2.0 + vLLM v0.11.2
**Symptom**: Worker crashes at VLM model init on any Blackwell-architecture card (compute capability 12.0). The pipeline backend is unaffected.

## What's blocked

- **RTX 5090** (SM120) — VLM backend crashes at `from_pretrained` time
- **RTX PRO 6000 Blackwell** (SM120) — same crash; RunPod groups it with Ada 6000 under `ADA_48_PRO`, which is why our `hub.json` default `gpuIds` excludes that pool
- **B200 / GB200** (SM100) — probably also broken on VLM; untested because RunPod doesn't expose these on serverless

Pipeline backend (`backend: "pipeline"`) doesn't use xformers/flash-attn and runs fine on Blackwell.

## Crash signature

```
compute_capability: 12.0 >= 8.0
INFO Starting to load model .../MinerU2.5-Pro-2605-1.2B/...
INFO Model loading took 2.16 GiB and 0.36 seconds
CUDA error (.../flash-attention/hopper/flash_fwd_launch_template.h:188): invalid argument
```

Root cause: xformers/flash-attention in vLLM v0.11.2 ships kernels for Ampere (8.x), Ada (8.9), and Hopper (9.0). No SM120 path. On Blackwell consumer cards, xformers misroutes to the Hopper kernel and crashes.

## Why we can't just bump vLLM

MinerU 3.2.x's `pyproject.toml`:

```toml
vllm = ["vllm>=0.10.1.1,<0.12"]
```

The first vLLM version with any Blackwell mention in release notes is **v0.13.0** (released 2025-12-19, SM103/GB300 Blackwell Ultra). Broader SM120 coverage lands in later releases (v0.14+). All Blackwell-aware vLLM versions are above MinerU's `<0.12` ceiling.

Verified 2026-05-27 against the `mineru-3.2.0-released` tag:
- MinerU 3.2.0 → still `vllm>=0.10.1.1,<0.12` (unchanged from 3.1.x)
- The 3.1→3.2 bump shipped a new VLM default (`Pro-2604` → `Pro-2605`) but did NOT loosen the vLLM ceiling
- Latest in-range vLLM: v0.11.2 (released 2025-11-20)
- No SM120 kernels in v0.11.x release notes; only SM100 (data-center Blackwell) MoE prep

## Unblock criteria

Watch for MinerU loosening their vLLM pin to `<0.13` or higher. Track:

- https://github.com/opendatalab/MinerU/blob/master/pyproject.toml
- https://pypi.org/project/mineru/ (look at any new 3.x release's `requires_dist` for vllm constraint)

When that lands, our migration is:

1. Bump `Dockerfile`'s `ARG VLLM_VERSION` to the lowest Blackwell-supporting version inside MinerU's new range
2. Re-check `allowedCudaVersions` — Blackwell hosts may need 13.1+ entries
3. Add `AMPERE_80`, `ADA_48_PRO`, and any Blackwell pool IDs back to `hub.json` `gpuIds` once we've smoke-tested
4. Update [docs/src/content/docs/guides/troubleshooting.mdx](../docs/src/content/docs/guides/troubleshooting.mdx) — remove the Blackwell-crash section
5. Update [docs/src/content/docs/guides/choosing-gpu.mdx](../docs/src/content/docs/guides/choosing-gpu.mdx) — update the `ADA_48_PRO` warning

## Workaround for users hit by this today

Either:
- Switch the affected job to `backend: "pipeline"` (works on Blackwell)
- Use a non-Blackwell pool (`ADA_24`, `AMPERE_24`, `AMPERE_48` — our defaults)

Already documented in [docs/src/content/docs/guides/troubleshooting.mdx](../docs/src/content/docs/guides/troubleshooting.mdx) under "VLM backend crashes on Blackwell GPUs".
