## [1.1.9](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.8...v1.1.9) (2026-05-20)

### Bug Fixes

* **hub:** drop ADA_48_PRO from default GPU pools; refresh template metadata ([ac0f5df](https://github.com/sergeyshmakov/runpod-mineru/commit/ac0f5dfa5dfcbf7b8b3e4af8f54ca340ed8865ed))
* **hub:** expose configurable env vars via hub.json deploy-time form ([9ef4ae4](https://github.com/sergeyshmakov/runpod-mineru/commit/9ef4ae4c2d0dab5471f2ff657e68c17a02a8ac70))
* **worker:** add S3 output mode + BUCKET_* env support ([2f2451e](https://github.com/sergeyshmakov/runpod-mineru/commit/2f2451e60480cb1ae5cc8ec55e6325b0440063c3))
* **worker:** align API with MinerU 3.1.x — parse_document, file_* fields, 5 backends, multi-format input, debug observability ([b763659](https://github.com/sergeyshmakov/runpod-mineru/commit/b763659b580206749179afc4013d5d9d5fd4a6ee))
* **worker:** bump MinerU to 3.1.x and vLLM base to v0.11.2; switch to RunPod Cached Models ([07efb50](https://github.com/sergeyshmakov/runpod-mineru/commit/07efb504987484a697bd97b63bf1aa1dbd6434b3))

### Documentation

* align all documentation with MinerU 3.1.x official recommendations ([bac4137](https://github.com/sergeyshmakov/runpod-mineru/commit/bac413720d1b27eab939a04725942fd512511d0b))
* four new guides + README quickstart, schema table, cross-links ([9b8a237](https://github.com/sergeyshmakov/runpod-mineru/commit/9b8a237bce5bd2f0a9a0da46d66599664d2fdc79))
* minor updates to docs ([db17801](https://github.com/sergeyshmakov/runpod-mineru/commit/db17801a6783fd12f8bb5ea32d3ce5fa96b96890))

## [1.1.9](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.8...v1.1.9) (2026-05-20)

### Bug Fixes

* **hub:** drop ADA_48_PRO from default GPU pools; refresh template metadata ([ac0f5df](https://github.com/sergeyshmakov/runpod-mineru/commit/ac0f5dfa5dfcbf7b8b3e4af8f54ca340ed8865ed))
* **hub:** expose configurable env vars via hub.json deploy-time form ([9ef4ae4](https://github.com/sergeyshmakov/runpod-mineru/commit/9ef4ae4c2d0dab5471f2ff657e68c17a02a8ac70))
* **worker:** add S3 output mode + BUCKET_* env support ([2f2451e](https://github.com/sergeyshmakov/runpod-mineru/commit/2f2451e60480cb1ae5cc8ec55e6325b0440063c3))
* **worker:** align API with MinerU 3.1.x — parse_document, file_* fields, 5 backends, multi-format input, debug observability ([b763659](https://github.com/sergeyshmakov/runpod-mineru/commit/b763659b580206749179afc4013d5d9d5fd4a6ee))
* **worker:** bump MinerU to 3.1.x and vLLM base to v0.11.2; switch to RunPod Cached Models ([07efb50](https://github.com/sergeyshmakov/runpod-mineru/commit/07efb504987484a697bd97b63bf1aa1dbd6434b3))

### Documentation

* align all documentation with MinerU 3.1.x official recommendations ([bac4137](https://github.com/sergeyshmakov/runpod-mineru/commit/bac413720d1b27eab939a04725942fd512511d0b))
* four new guides + README quickstart, schema table, cross-links ([9b8a237](https://github.com/sergeyshmakov/runpod-mineru/commit/9b8a237bce5bd2f0a9a0da46d66599664d2fdc79))

## [1.1.8](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.7...v1.1.8) (2026-05-19)

### Bug Fixes

* **client:** omit None end_page from payload; better error message fallback ([52dbc53](https://github.com/sergeyshmakov/runpod-mineru/commit/52dbc53ec3cf8499f16a157273f12f55477232c0))

## [1.1.7](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.6...v1.1.7) (2026-05-19)

### Bug Fixes

* **hub:** add test_input.json + switch pip to uv for faster builds ([561f7e7](https://github.com/sergeyshmakov/runpod-mineru/commit/561f7e7452c0419909c6faf638c318cef2a5f717))
* **hub:** set MINERU_VL_MODEL_NAME so the local vlm backend loads Pro-2604 ([1abd2ba](https://github.com/sergeyshmakov/runpod-mineru/commit/1abd2ba4eedef5f70f81fd755d806b83ce32e608))

## [1.1.6](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.5...v1.1.6) (2026-05-19)

### Bug Fixes

* **hub:** use python3 instead of python in Dockerfile ([3b0e778](https://github.com/sergeyshmakov/runpod-mineru/commit/3b0e778aa1479e8779edd75e1ba660e6542cf321))

## [1.1.5](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.4...v1.1.5) (2026-05-19)

### Bug Fixes

* **hub:** pre-cache MinerU weights in image; bump test timeout to 20 min ([3bbef3a](https://github.com/sergeyshmakov/runpod-mineru/commit/3bbef3ad62c2836d1128492fa295ab63014ad56b))

## [1.1.4](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.3...v1.1.4) (2026-05-19)

### Bug Fixes

* **hub:** switch test GPU from RTX 4090 to RTX A5000 ([be7a262](https://github.com/sergeyshmakov/runpod-mineru/commit/be7a26223507ada4cf783904abd0969b09e1a90d))
* **hub:** widen allowedCudaVersions to ease GPU supply constraints ([cc34711](https://github.com/sergeyshmakov/runpod-mineru/commit/cc347113f7b4d16a82bccdfe9f5c86e3452c6fad))

### Documentation

* update docs site styles ([75ced01](https://github.com/sergeyshmakov/runpod-mineru/commit/75ced01ee83212adcf4c854e4df23a7312facafe))

## [1.1.3](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.2...v1.1.3) (2026-05-19)

### Bug Fixes

* **hub:** correct GPU pool IDs (ADA_48 → ADA_48_PRO) ([844f1be](https://github.com/sergeyshmakov/runpod-mineru/commit/844f1befcf45bd0a24c10905d429d3aa531e5dc5))

### Documentation

* update docs stylings ([c512a90](https://github.com/sergeyshmakov/runpod-mineru/commit/c512a90ecb67d3d2de05b1845f5cfa1269821140))

## [1.1.2](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.1.1...v1.1.2) (2026-05-19)

### Bug Fixes

* **hub:** align manifests with official template schema ([bc3903b](https://github.com/sergeyshmakov/runpod-mineru/commit/bc3903b1f239f8f6eccc64b1f6a8c631cfe487f9))

### Documentation

* update docs links ([6a7be0a](https://github.com/sergeyshmakov/runpod-mineru/commit/6a7be0ad998389e9bb263e395cc435316e56ce58))

## [1.1.0](https://github.com/sergeyshmakov/runpod-mineru/compare/v1.0.0...v1.1.0) (2026-05-19)

### Features

* **docs:** add Choosing a GPU guide ([3aa6506](https://github.com/sergeyshmakov/runpod-mineru/commit/3aa650650fa91a79472b25f76e027428a7b93752))

## 1.0.0 (2026-05-19)

### Features

* **docs:** scaffold Astro + Starlight site with launch blog post ([aaeaa27](https://github.com/sergeyshmakov/runpod-mineru/commit/aaeaa27eed2912928fc068b44b7709842714a482))
* prepare runpod-mineru for public RunPod Hub launch ([9690fe9](https://github.com/sergeyshmakov/runpod-mineru/commit/9690fe9956665dfe0d53cec494c541c1ce5a398e))

# Changelog

All notable changes to this project will be documented in this file.

This file is **maintained automatically** by [semantic-release](https://semantic-release.gitbook.io/) from the commit history. Do not edit it by hand — commit using [Conventional Commits](https://www.conventionalcommits.org/) and the next release will append the right entry.

<!-- semantic-release-replace-marker — DO NOT REMOVE -->
