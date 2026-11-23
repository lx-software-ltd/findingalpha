# Plan: Dry-run the public website deploy

**Status**: In progress
**Zone**: red

## Goal

Call `s3-cloudfront-deploy` for the findingalpha public site, pinned to actions `e6be2629d7206b0d5c079662f364772bc816acc1`. The first run on `main` is a dry run. It prints the planned S3 changes from the shared action and from the current deploy script, and fails when those lists differ. It does not upload and it does not invalidate CloudFront.

## Non-goals

- No real switch. `dry-run` stays true until the `main` run is compared.
- No other site, and no Amplify caller.
- No edit to `scripts/deploy/deploy-public-website.sh`. The workflow wraps `aws` so that script's S3 commands are `--dryrun` and its invalidation is skipped.

## Files

`.github/workflows/deploy-public-website.yml`, `scripts/test_workflow_secrets.py`, `docs/deployment/public-website.md`.

## Invariants this change preserves

- The job still runs only on `main`, after the build, and only when `findingalpha-public-www` exists.
- Credentials still come from `aws-oidc` with `secrets.AWS_ACCOUNT_ID`.
- The caller still resolves the bucket and distribution. The action does not read the stack.

## Done when

`python3 -m unittest scripts/test_workflow_secrets.py` passes. After merge, the `main` dry run's planned changes match. Only then does a follow-up set `dry-run` to false and stop calling the shell script.

## Rollback

Revert the pull request. The next `main` run uses `scripts/deploy/deploy-public-website.sh` again.

## Open questions

None.
