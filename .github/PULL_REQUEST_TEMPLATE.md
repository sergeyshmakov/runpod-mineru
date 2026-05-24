<!--
Thanks for the PR. A few quick things to confirm:
-->

## Summary

<!-- One or two sentences. What changed and why. -->

## Conventional Commit type

<!--
Choose one — the squashed commit message must start with it, OR the PR must
contain at least one commit with this prefix so semantic-release picks it up:

  feat:     new feature (triggers minor bump)
  fix:      bug fix (triggers patch bump)
  perf:     performance improvement (patch)
  refactor: non-behaviour change (patch)
  docs:     documentation only (no release; docs(readme) does trigger patch)
  test:     tests only (no release)
  build:    Dockerfile / requirements (no release)
  ci:       GitHub Actions workflows (no release)
  chore:    anything else (no release)

While the template is pre-1.0 and has no documented users, use `fix:` (patch
bump) even for API rewrites, default-behaviour changes, and dependency major
bumps. Do NOT use the explicit major-bump markers — those trigger a major
version bump for changes that, to the (nonexistent) user base, look like the
project being made more correct. Describe the break in the body instead.
Revisit once we have users.
-->

- [ ] `feat` `fix` `perf` `refactor` `docs` `test` `build` `ci` `chore`

## Surface area

<!-- Which parts of the template does this touch? -->

- [ ] `handler.py` (worker job input/output contract)
- [ ] `mineru_client/` (Python client API)
- [ ] `Dockerfile` / `requirements.txt`
- [ ] `.runpod/hub.json` (disabled Hub listing, env array, GPU pools)
- [ ] `deploy.py`
- [ ] Docs (`docs/`, README, CONTRIBUTING, blog)
- [ ] Tests

## Checklist

- [ ] Tests pass locally: `pip install -e ".[test]" && pytest`
- [ ] New code paths have at least one test (CPU-only; CI has no GPU).
- [ ] If touching the wire contract: handler docstring AND `docs/src/content/docs/reference/api.mdx` both updated.
- [ ] If adding an env var: it's in `.runpod/hub.json` `env` array AND the Dockerfile/docs reference it.
- [ ] No secrets in the diff (`.env`, `RUNPOD_API_KEY`, `HF_TOKEN`, `BUCKET_*`).
- [ ] `CHANGELOG.md` is **not** edited by hand — semantic-release will append the right entry on merge.

## How to test

<!--
Either real commands you ran, or "tests cover this". If the change is operator-
facing (deploy.py / Dockerfile / endpoint config), include the exact `deploy.py`
command you used and a one-line summary of the RunPod dashboard state. If the
change is handler-side, paste the `debug` block from a real response so we can
verify backend / model_dir / GPU.
-->
