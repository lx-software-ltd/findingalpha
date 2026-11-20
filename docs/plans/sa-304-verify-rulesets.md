# Plan: Pin Verify GitHub Rulesets

**Status**: In progress
**Zone**: yellow

Parent plan: [Shared actions repository and CI convergence](https://github.com/lx-software-ltd/actions/blob/61d2a581a1d880533982bada88923ad1b6431700/docs/plans/shared-actions-and-ci-convergence.md), step SA-304.

A pull request is opened.

## Goal

Replace the inline ruleset script with the composite action so this repository takes gate G1 before the same contract lands on the repositories whose Monday run fails.

The Monday failure this fixes is on evolvesprouts and siutindei, not this repository. This pilot takes the same contract before those two.

Gate G1: expected reviews exactly 0, required checks exactly lint and test.

Pin:

`lx-software-ltd/actions/verify-rulesets@61d2a581a1d880533982bada88923ad1b6431700` # main 2026-11-20

## Non-goals

No other workflow. No run of this workflow from the pull request, from `workflow_dispatch`, or from the Monday schedule. No require-jobs, setup-node, or setup-python pin change.

## Files

- `.github/workflows/verify-rulesets.yml`
- `docs/architecture/security.md`
- `docs/plans/sa-304-verify-rulesets.md`

Deleted:

- `scripts/verify_github_rulesets.py`
- `scripts/test_verify_github_rulesets.py`

Search of the tree found no other workflow, test runner, or import that calls those files. `test.yml` discovers `scripts/test_*.py`, so deleting the test removes it from that discover. The branch-protection section names the pinned action.

## Invariants this change preserves

The workflow name stays Verify GitHub Rulesets. The schedule stays cron `0 9 * * 1`. `workflow_dispatch` stays. Permissions stay `contents: read`. The job id stays `verify-branch-protection` with no job name, so the check name stays `verify-branch-protection`. The runner stays `ubuntu-26.04`. The checkout step stays `actions/checkout@v7`.

This workflow does not run on `pull_request`, so the pull request will not execute it.

## Check names this pull request adds

This pull request deletes files under `scripts/`. `lint.yml` and `test.yml` path filters include `scripts/**`. Those workflows run on the pull request because the `pull_request` trigger has no path filter. `verify-rulesets.yml` does not run on `pull_request`, so the pull request will not execute it.

Job names from the job `name` fields:

- Admin Web viewport smoke
- Build Admin Web
- Build CDK
- Build Public Www
- Check shared contracts
- Lint Admin Web
- Lint Public Www
- Lint Python
- Test Infrastructure
- Test Python
- Validate agent harness
- lint
- test

`lint` and `test` stay present.

## Done when

The verify step uses the pin above and passes `token` from `github.token`, `expected-reviews` `"0"`, and `required-checks` `lint test`. The two scripts are gone, and no test imports the deleted module.

Check-run names recorded on main `11407a5725c8ac97fb1d9b8ba92d3a69d195a34d` before the edit, from `gh api repos/lx-software-ltd/findingalpha/commits/11407a5725c8ac97fb1d9b8ba92d3a69d195a34d/check-runs` (`total_count` 8):

- Check Node.js lockfiles
- Checkov IaC Security
- CodeQL Analysis (javascript)
- CodeQL Analysis (python)
- PII denylist
- Secret Scanning
- Security Summary
- Semgrep SAST

## Rollback

Revert the pull request.

## Open questions

None.
