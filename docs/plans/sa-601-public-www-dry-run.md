# Plan: Dry-run the public website deploy

**Status**: In progress
**Zone**: red

## Goal

Call `s3-cloudfront-deploy` for the findingalpha public site. Workflow conformance allows one `lx-software-ltd/actions` commit, so every pin and the pre-commit `rev` move from `c210c3223782894251ba37b4fc71a0c245619d39` to `e6be2629d7206b0d5c079662f364772bc816acc1`. The actions between those commits add deploy actions. They do not change the actions this repository already calls. Before the existing deploy step, a comparison dry-runs the shared action and the current script. That step is `continue-on-error: true`, so a mismatch is reported and the script still uploads.

## Non-goals

- No real switch. The upload step stays `scripts/deploy/deploy-public-website.sh`.
- No other site, and no Amplify caller.
- No edit to `scripts/deploy/deploy-public-website.sh`. The workflow wraps `aws` so that script's S3 commands are `--dryrun` and its invalidation is skipped.

## Files

`.github/workflows/`, `.pre-commit-config.yaml`, `scripts/test_workflow_secrets.py`, `docs/deployment/public-website.md`.

## Invariants this change preserves

- The job still runs only on `main`, after the build, and only when `findingalpha-public-www` exists.
- Credentials still come from `aws-oidc` with `secrets.AWS_ACCOUNT_ID`.
- The caller still resolves the bucket and distribution. The action does not read the stack.

## Done when

`python3 -m unittest scripts/test_workflow_secrets.py` passes. After merge, a hand run of Deploy Public Website on `main` prints `Dry run matches the current deploy (N planned S3 changes)` and the script still uploads. Only then does a follow-up replace the script with the action.

## Rollback

Revert the pull request. The next `main` run uses `scripts/deploy/deploy-public-website.sh` again.

## Open questions

None.
