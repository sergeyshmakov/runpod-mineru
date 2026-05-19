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

Append `!` or include a `BREAKING CHANGE:` footer for major bumps.
-->

- [ ] `feat` `fix` `perf` `refactor` `docs` `test` `build` `ci` `chore`

## Checklist

- [ ] Tests pass locally: `pip install -e ".[test]" && pytest`
- [ ] New code paths have at least one test (CPU-only; CI has no GPU).
- [ ] The handler's wire contract in `handler.py`'s docstring is unchanged, OR this PR is marked breaking.
- [ ] `CHANGELOG.md` is **not** edited by hand — semantic-release will append the right entry on merge.

## How to test

<!--
Either real commands you ran, or "tests cover this". If the change is operator-
facing (deploy.py / Dockerfile / endpoint config), include the exact `deploy.py`
command you used and a one-line summary of the RunPod dashboard state.
-->
