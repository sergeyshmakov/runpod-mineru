# runpod-mineru

<!-- badges: ci, license, python, runpod -->
[![CI](https://github.com/sergeyshmakov/runpod-mineru/actions/workflows/ci.yml/badge.svg)](https://github.com/sergeyshmakov/runpod-mineru/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![MinerU](https://img.shields.io/badge/MinerU-2.5-purple)](https://github.com/opendatalab/MinerU)
[![Deploy on RunPod](https://img.shields.io/badge/Deploy-RunPod-7c3aed?logo=runpod&logoColor=white)](https://runpod.io?ref=31jdfpnq)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-fa6673.svg)](https://www.conventionalcommits.org/)

Serverless [MinerU 2.5](https://github.com/opendatalab/MinerU) PDF parser on [RunPod](https://runpod.io?ref=31jdfpnq). Scales to zero, ~$0.0001 per page, ten minutes from sign-up to first parse.

**[📚 Docs](https://sergeyshmakov.github.io/runpod-mineru/)**  ·  **[🚀 Deploy on RunPod Hub](https://runpod.io?ref=31jdfpnq)**  ·  **[📝 Blog](https://sergeyshmakov.github.io/runpod-mineru/blog/)**

## 30-second taste

```python
from mineru_client import MineruClient

client = MineruClient(endpoint_id="<your-endpoint-id>")
result = client.parse_pdf(pdf_url="https://example.com/report.pdf", end_page=4)
client.save_tarball(result, "./out/doc")
# → markdown + content_list + middle.json + images
```

## Why this exists

- **MinerU 2.5** is SOTA for PDF → structured Markdown/JSON: charts, tables, math, 84 languages. Apache 2.0 with explicit commercial thresholds. See the [paper](https://arxiv.org/abs/2604.04771), [repo](https://github.com/opendatalab/MinerU), and [model card](https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B).
- **RunPod Serverless** bills per-second and scales to zero. A 100-page document costs roughly $0.01 instead of paying for an always-on GPU.
- **You don't have to wire any of that together yourself.** Deploy from the [RunPod Hub](https://runpod.io?ref=31jdfpnq) in one click, or fork this repo for full control.

## Two ways to integrate

### A. Quick start with `MineruClient`

A small Python wrapper that lives in this repo. Best for prototyping and single-user scripts.

```powershell
pip install "mineru-client @ git+https://github.com/sergeyshmakov/runpod-mineru@v1.1.0"
```

```python
from mineru_client import MineruClient
client = MineruClient(endpoint_id="<your-endpoint-id>")
result = client.parse_pdf(pdf_url="https://example.com/report.pdf")
```

### B. Production with RunPod SDK / HTTP

For high-throughput, async, or non-Python callers. Hit the endpoint directly using the documented [JSON payload contract](https://sergeyshmakov.github.io/runpod-mineru/reference/api/).

```python
import runpod
runpod.api_key = "..."
endpoint = runpod.Endpoint("<endpoint-id>")
result = endpoint.run_sync({"input": {"pdf_url": "https://example.com/report.pdf"}})
```

Prototype with A; switch to B once you need async, retries, or multi-language callers. See [Clients](https://sergeyshmakov.github.io/runpod-mineru/getting-started/clients/) for the full comparison.

## How does it compare?

Parsing accuracy is MinerU's domain; their published [OmniDocBench](https://github.com/opendatalab/OmniDocBench) leaderboard puts the 1.2B VLM ahead of much larger general-purpose models:

[![MinerU 2.5 leaderboard](https://hotelll.github.io/MinerU2.5-Pro/leaderboard.png)](https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B)

<sub>Source: [MinerU2.5-Pro-2604-1.2B model card](https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B) and the [MinerU 2.5 technical report](https://arxiv.org/abs/2604.04771).</sub>

| | runpod-mineru (this) | Marker | GROBID | Nougat |
|---|---|---|---|---|
| Scale-to-zero | ✅ | ⚠️ possible via serverless | ❌ (always-on) | ❌ |
| GPU support | GPU only | CPU or GPU | CPU | GPU required |
| Tables | ✅ structured | ⚠️ noisy | ⚠️ refs only | ⚠️ |
| Equations | ✅ LaTeX | ✅ LaTeX | ❌ | ✅ LaTeX |
| Multi-lang | ✅ 84 langs | ⚠️ Latin-heavy | EN only | EN/limited |
| Setup time | 5 min | 10 min | 30 min | 20 min |
| License | Apache 2.0 + attribution\* | **GPL-3.0 code + modified RAIL-M weights**\*\* | Apache 2.0 | MIT code + **CC-BY-NC weights** |
| Commercial SaaS | ✅ free below thresholds\* | ❌ **blocked for competing services**\*\* | ✅ free | ❌ **blocked** (non-commercial weights) |

<sub>\*MinerU 2.5 is Apache 2.0 with an addendum: free commercial use up to 100M MAU and $20M monthly revenue, with attribution required in UI/docs. See the [MinerU LICENSE](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md).</sub>

<sub>\*\*Marker's code is GPL-3.0; its OCR engine (Surya) ships under modified RAIL-M weights. RAIL-M's commercial clause bars use by any entity that "provides…any product or service that competes with…Licensor" — i.e. a competing PDF-parsing API/SaaS is barred regardless of company size or revenue. Datalab also ships Chandra (the model their hosted API runs) as a separate library under the same modified RAIL-M weights license. See [Surya MODEL_LICENSE](https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE) and [Chandra MODEL_LICENSE](https://github.com/datalab-to/chandra/blob/master/MODEL_LICENSE).</sub>

The license row is the load-bearing one for production SaaS. Marker's combination of GPL-3.0 code and RAIL-M weights blocks anyone building a competing PDF-extraction product, regardless of size; the RAIL-M competitor clause applies even to startups under the $2M revenue/funding thresholds. Nougat's model weights are CC-BY-NC 4.0, legally unusable for any paid product without a separate Meta agreement. GROBID is cleanly Apache 2.0 but is English-only and equations-blind. MinerU 2.5 is the only one of the four with both production-grade accuracy AND a license that permits competing commercial SaaS use.

## Documentation

Everything below the surface lives on the docs site:

- **[Overview](https://sergeyshmakov.github.io/runpod-mineru/getting-started/overview/)** — what it is, who it's for, architecture
- **[Deploy](https://sergeyshmakov.github.io/runpod-mineru/getting-started/deploy/)** — Hub one-click, fork-and-build, or BYO image
- **[Clients](https://sergeyshmakov.github.io/runpod-mineru/getting-started/clients/)** — Python `MineruClient` vs. direct RunPod SDK
- **[Choosing a GPU](https://sergeyshmakov.github.io/runpod-mineru/guides/choosing-gpu/)** — workload-to-pool map, when to bump VRAM
- **[API reference](https://sergeyshmakov.github.io/runpod-mineru/reference/api/)** — JSON payload contract, response shapes, validation rules
- **[Blog](https://sergeyshmakov.github.io/runpod-mineru/blog/)** — launch posts and project notes

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Commits follow [Conventional Commits](https://www.conventionalcommits.org/); commitlint enforces this in CI and `CHANGELOG.md` is generated automatically by semantic-release on push to `main`.

## Support this project

If this saves you time, the cheapest way to support development is to **[sign up for RunPod through this link](https://runpod.io?ref=31jdfpnq)**. Costs you nothing extra and lets the maintainer keep iterating.

## License

[MIT](LICENSE). The underlying [MinerU 2.5](https://github.com/opendatalab/MinerU) is Apache-2.0; the [RunPod SDK](https://github.com/runpod/runpod-python) is MIT.
