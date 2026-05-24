# mineru-runpod

<!-- badges: ci, license, python, runpod -->
[![CI](https://github.com/sergeyshmakov/mineru-runpod/actions/workflows/ci.yml/badge.svg)](https://github.com/sergeyshmakov/mineru-runpod/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![MinerU](https://img.shields.io/badge/MinerU-3.1-purple)](https://github.com/opendatalab/MinerU)
[![Runpod](https://api.runpod.io/badge/sergeyshmakov/mineru-runpod)](https://console.runpod.io/hub/sergeyshmakov/mineru-runpod)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fa6673.svg)](https://www.conventionalcommits.org/)

Serverless [MinerU](https://github.com/opendatalab/MinerU) PDF parser on [RunPod](https://runpod.io?ref=31jdfpnq). MinerU 3.1.x runtime with the `MinerU2.5-Pro-2604-1.2B` VLM. Scales to zero, ~$0.0003 per page on 24 GB Ampere serverless, ten minutes from sign-up to first parse.

**📚 [Docs](https://sergeyshmakov.github.io/mineru-runpod/)**  ·  **🚀 [Deploy on RunPod Hub](https://runpod.io?ref=31jdfpnq)**  ·  **📝 [Blog](https://sergeyshmakov.github.io/mineru-runpod/blog/)**

## 30-second taste

Pick your transport. Either of these works.

**Python (`mineru_client`):**

```python
from mineru_client import MineruClient

client = MineruClient(endpoint_id="<your-endpoint-id>")
result = client.parse_document(file_url="https://example.com/report.pdf", end_page=4)
client.save_tarball(result, "./out/doc")
# → markdown + content_list + middle.json + images
```

**curl (no SDK):**

```sh
curl -X POST "https://api.runpod.ai/v2/<endpoint-id>/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"file_url":"https://example.com/report.pdf","end_page":4,"return":"inline"}}'
```

The response includes a top-level `markdown` field with the full Markdown rendering of the document. Pipe it straight to a file: `curl ... | jq -r '.output.markdown' > report.md`.

Accepts PDF, image (PNG/JPEG/GIF/BMP/TIFF/WebP), DOCX, PPTX, XLSX. Three return modes: `tarball_b64` (default — base64 tarball containing `{basename}.md` + structured JSON + images), `inline` (markdown + content_list + middle + images returned as separate response fields), or `s3` (presigned URL for outputs that would exceed RunPod's ~20 MB response cap — requires `BUCKET_*` env vars on the endpoint).

## Why this exists

- **MinerU** is SOTA for PDF → structured Markdown/JSON: charts, tables, math, 109 languages. Apache 2.0 with explicit commercial thresholds. See the [paper](https://arxiv.org/abs/2604.04771), [repo](https://github.com/opendatalab/MinerU), and [model card](https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B).
- **RunPod Serverless** bills per-second and scales to zero. A 100-page document costs roughly $0.03 on 24 GB Ampere serverless instead of paying for an always-on GPU. See [RunPod pricing](https://www.runpod.io/pricing) for current rates.
- **You don't have to wire any of that together yourself.** Deploy from the [RunPod Hub](https://runpod.io?ref=31jdfpnq) in one click, or fork this repo for full control.

## Two ways to integrate

### A. Quick start with `MineruClient`

A small Python wrapper that lives in this repo. Best for prototyping and single-user scripts.

```powershell
pip install "mineru-client @ git+https://github.com/sergeyshmakov/mineru-runpod@v1.1.0"
```

```python
from mineru_client import MineruClient
client = MineruClient(endpoint_id="<your-endpoint-id>")
result = client.parse_document(file_url="https://example.com/report.pdf")
```

### B. Production with RunPod SDK / HTTP

For high-throughput, async, or non-Python callers. Hit the endpoint directly using the documented [JSON payload contract](https://sergeyshmakov.github.io/mineru-runpod/reference/api/).

```python
import runpod
runpod.api_key = "..."
endpoint = runpod.Endpoint("<endpoint-id>")
result = endpoint.run_sync({"input": {"file_url": "https://example.com/report.pdf"}})
```

Prototype with A; switch to B once you need async, retries, or multi-language callers. See [Clients](https://sergeyshmakov.github.io/mineru-runpod/getting-started/clients/) for the full comparison.

## API at a glance

Full reference: [docs site](https://sergeyshmakov.github.io/mineru-runpod/reference/api/) and the docstring atop [`handler.py`](handler.py). Summary table:

| Field | Required | Default | Notes |
|---|---|---|---|
| `file_url` / `file_b64` / `volume_path` | exactly one | — | Public URL, base64 bytes, or container path. Worker auto-detects format. |
| `start_page` | no | `0` | 0-based inclusive (PDF only) |
| `end_page` | no | `-1` | 0-based inclusive; `-1` = end of doc |
| `lang` | no | `"en"` | Pipeline backend only. Script-family code: `east_slavic`, `cyrillic`, `latin`, `arabic`, `devanagari`, `japan`, `korean`, etc. |
| `backend` | no | `"vlm-auto-engine"` | `pipeline` / `vlm-auto-engine` / `vlm-http-client` / `hybrid-auto-engine` / `hybrid-http-client` |
| `server_url` | iff `*-http-client` | — | URL of an external vLLM OpenAI-compatible server |
| `formula_enable` / `table_enable` | no | `true` | Extract LaTeX / structured HTML tables |
| `return` | no | `"tarball_b64"` | `"tarball_b64"` / `"inline"` / `"s3"` |
| `basename` | no | `"doc"` | Filename stem; alphanumeric + `-_` |

Success response always includes `ok=true`, `elapsed_seconds`, `pages_processed`, `mineru_version`, `source`, and a `debug` block (`backend`, `input_format`, `model_dir`, `gpu`, `phase_ms`). Output payload depends on `return`:

- `"tarball_b64"` → `tarball_b64` (base64 .tar.gz)
- `"inline"` → `markdown` + `content_list` + `middle` + `images` (each value base64)
- `"s3"` → `tarball_url` (presigned, ~1 h) + `tarball_url_expires_in` + `bucket_key`

Errors: top-level `error` + `ok=false` + `traceback` + the same `debug` block.

## How does it compare?

Parsing accuracy is MinerU's domain; their published [OmniDocBench](https://github.com/opendatalab/OmniDocBench) leaderboard puts the 1.2B VLM ahead of much larger general-purpose models:

[![MinerU 2.5 leaderboard](https://hotelll.github.io/MinerU2.5-Pro/leaderboard.png)](https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B)

<sub>Source: [MinerU2.5-Pro-2604-1.2B model card](https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B) and the [MinerU 2.5 technical report](https://arxiv.org/abs/2604.04771).</sub>

| | mineru-runpod (this) | Marker | GROBID | Nougat |
|---|---|---|---|---|
| Scale-to-zero | ✅ ready to use | ⚠️ possible, needs extra setup | ❌ (always-on) | ❌ |
| GPU support | GPU only | CPU or GPU | CPU | GPU required |
| Equations | ✅ LaTeX | ✅ LaTeX | ❌ | ✅ LaTeX |
| Multi-lang | ✅ 109 langs (pipeline backend) | per upstream README | EN only | per upstream README |
| Setup time | 5 min | 10 min | 30 min | 20 min |
| License | Apache 2.0 + attribution\* | **GPL-3.0 code + modified RAIL-M weights**\*\* | Apache 2.0 | MIT code + **CC-BY-NC 4.0 weights** |
| Commercial SaaS | ✅ free below thresholds\* | ⚠️ depends on RAIL-M competitor clause\*\* | ✅ free | ⚠️ subject to CC-BY-NC non-commercial clause |

<sub>\*MinerU is Apache 2.0 with an addendum: free commercial use up to 100M MAU and $20M monthly revenue, with attribution required in UI/docs. See the [MinerU LICENSE](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md).</sub>

<sub>\*\*Marker's code is GPL-3.0; its OCR engine (Surya) ships under a modified RAIL-M licence whose §2(c) prohibits use by entities that "provide … any product or service that competes with … Licensor." Datalab's own README says Marker is free for "startups under $2M funding/revenue" — that carveout doesn't appear in the literal licence text, so the two read differently. Verify the current licence against your own usage with counsel before depending on Marker for a competing service. Datalab ships [Chandra](https://github.com/datalab-to/chandra) (the model behind their hosted API) under the same modified RAIL-M licence. See [Surya MODEL_LICENSE](https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE) and [Chandra MODEL_LICENSE](https://github.com/datalab-to/chandra/blob/master/MODEL_LICENSE).</sub>

The license row matters most for production SaaS. Marker pairs GPL-3.0 code with modified RAIL-M weights whose competitor clause is at least ambiguous about commercial reach; Datalab's marketing and the literal license text say different things, so plan for legal review. Nougat's model weights are CC-BY-NC 4.0 — Creative Commons' definition of non-commercial use is fuzzy at the edges, and deploying Nougat as part of a paid service is plainly outside it. GROBID is cleanly Apache 2.0 but is English-only and equations-blind. MinerU is the only one of the four with both production-grade accuracy AND a license whose commercial reach is documented in clear, quantitative terms (100M MAU and $20M monthly revenue thresholds).

## Documentation

Everything below the surface lives on the docs site:

- **[Overview](https://sergeyshmakov.github.io/mineru-runpod/getting-started/overview/)** — what it is, who it's for, architecture
- **[Deploy](https://sergeyshmakov.github.io/mineru-runpod/getting-started/deploy/)** — Hub one-click, fork-and-build, or BYO image
- **[Clients](https://sergeyshmakov.github.io/mineru-runpod/getting-started/clients/)** — Python `MineruClient` vs. direct RunPod SDK
- **[Choosing a GPU](https://sergeyshmakov.github.io/mineru-runpod/guides/choosing-gpu/)** — workload-to-pool map, when to bump VRAM
- **[API reference](https://sergeyshmakov.github.io/mineru-runpod/reference/api/)** — JSON payload contract, response shapes, validation rules
- **[Blog](https://sergeyshmakov.github.io/mineru-runpod/blog/)** — launch posts and project notes

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Commits follow [Conventional Commits](https://www.conventionalcommits.org/); commitlint enforces this in CI and `CHANGELOG.md` is generated automatically by semantic-release on push to `main`.

## Support this project

If this saves you time, the cheapest way to support development is to **[sign up for RunPod through this link](https://runpod.io?ref=31jdfpnq)**. Costs you nothing extra and lets the maintainer keep iterating.

## License

[MIT](LICENSE). The underlying [MinerU](https://github.com/opendatalab/MinerU) is Apache-2.0; the [RunPod SDK](https://github.com/runpod/runpod-python) is MIT.
