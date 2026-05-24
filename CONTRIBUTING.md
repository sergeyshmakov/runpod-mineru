# Contributing to mineru-runpod

Thanks for considering a contribution. This project is intentionally a thin wrapper — most of the actual document-parsing work happens upstream in [MinerU](https://github.com/opendatalab/MinerU). Please route your issue to the right place:

## What this repo is responsible for

- The RunPod serverless worker (`handler.py`)
- The Python client (`mineru_client/`)
- Deploy / destroy scripts
- The Dockerfile + dependency pinning

## What this repo is *not* responsible for

- **Parsing accuracy / quality** of MinerU's output → file at [opendatalab/MinerU](https://github.com/opendatalab/MinerU/issues).
- **RunPod platform behaviour** (endpoint won't scale, FlashBoot misbehaves, cold start too long) → RunPod support.
- **vLLM / CUDA issues** → vLLM upstream.

If you're not sure, open an issue here and we'll redirect.

## Bug reports

Please include:
- The exact `deploy.py` command you ran (with secrets redacted)
- The `MineruClient.parse_document(...)` call (input shape, not the file contents itself)
- The full handler response — especially the `error` and `traceback` fields if `ok: false`
- The MinerU version reported in the response (`mineru_version`)
- The RunPod endpoint id and approximate timestamp so we can correlate with platform logs if needed

## Pull requests

- Keep PRs small and focused. Independent bug fix + refactor = two PRs.
- Run the test suite locally: `pip install -e ".[test]" && pytest -v`.
- New code paths need at least one test. CPU-only tests, please — CI doesn't have a GPU.
- Don't break the wire contract documented in `handler.py`'s docstring without a major version bump (`fix!`/`feat!` or `BREAKING CHANGE:` footer).
- `CHANGELOG.md` is maintained by semantic-release — do **not** edit it by hand. Write a good commit message instead (see below).

## Commit message format — Conventional Commits

We use [Conventional Commits](https://www.conventionalcommits.org/) so version bumps and changelog entries are generated automatically.

```
type(optional-scope): short summary in present tense

optional body explaining the why, wrapped at ~80 cols

optional footer(s)
```

Types that **trigger a release**:

| Type | Bump | Example |
|---|---|---|
| `feat:` | minor | `feat(client): add streaming response support` |
| `fix:` | patch | `fix(handler): handle PDFs with empty page_range` |
| `perf:` | patch | `perf(handler): stream tarball instead of buffering` |
| `refactor:` | patch | `refactor(client): split parse_document into smaller helpers` |
| `revert:` | patch | `revert: revert "feat: streaming response"` |

Types that **do not** trigger a release:

| Type | Use for |
|---|---|
| `docs:` | doc-only changes (`docs(readme):` triggers a patch though) |
| `test:` | adding/refactoring tests |
| `build:` | Dockerfile, requirements.txt, dep bumps |
| `ci:` | GitHub Actions workflows |
| `chore:` | anything else (housekeeping) |
| `style:` | formatting only |

**Breaking changes** force a major bump regardless of type:

```
feat(client)!: rename parse_document to parse

BREAKING CHANGE: parse_document is now parse. Callers must update imports.
```

Commitlint runs on every PR — bad messages will be rejected. Locally you can preview with `npx commitlint --from HEAD~1 --to HEAD --verbose`.

## Stability guarantees

After v1.0.0:
- The handler's job input/output schema is semver-versioned.
- The `MineruClient` public method signatures follow semver.
- Anything prefixed `_` is private; expect it to change.

Before v1.0.0 (we are here): minor breakage may happen between 0.x releases, documented in `CHANGELOG.md`.

## Code style

No enforced formatter yet — just match the existing style. Type hints encouraged, not required.

## License

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE) of this repo.
