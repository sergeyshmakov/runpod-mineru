# Security policy

## Reporting a vulnerability

Please use [GitHub Security Advisories](https://github.com/sergeyshmakov/mineru-runpod/security/advisories/new) to report security issues privately. Do **not** open public issues for security problems.

You should expect an initial response within 5 working days.

## Scope

In scope:
- Code injection / unsafe deserialization in `handler.py` or `mineru_client/`
- Path traversal via `volume_path` or `basename`
- Malicious input bytes (PDF / image / DOCX / PPTX / XLSX) that bypass `_detect_format` and reach MinerU in an unexpected code path
- Resource exhaustion via crafted input that bypasses the documented limits (`MAX_INLINE_FILE_MB`, page-range bounds, etc.)
- Exposure of `RUNPOD_API_KEY`, `HF_TOKEN`, or `BUCKET_*` credentials through the code paths in this repo or in worker logs / responses
- S3 upload path: presigned URL leakage, bucket-key collisions, signature replay

Out of scope (please report upstream):
- Vulnerabilities in [MinerU](https://github.com/opendatalab/MinerU) — report to opendatalab
- Vulnerabilities in vLLM, boto3, RunPod platform, the base Docker image, or transitive Python dependencies — report to their respective maintainers

## Hardening notes for operators

- Always set `RUNPOD_API_KEY`, `HF_TOKEN`, `BUCKET_SECRET_ACCESS_KEY` via environment variables; never commit them. `.env` is `.gitignore`d but be careful with shell history.
- Treat `volume_path` as a privileged input — only mount volumes you control, and validate paths in any caller code that builds them from user input.
- For `return: "s3"`: treat the presigned URL as a short-lived bearer credential. Default lifetime is 1 hour (`_S3_PRESIGN_TTL_SECONDS` in `handler.py`). Don't log the URL.
- Set `execution_timeout` low enough to prevent a stuck job from costing you a runaway GPU bill.
