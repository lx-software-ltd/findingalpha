# Plan: Dry-run the admin website deploy

**Status**: In progress
**Zone**: red

## Goal

Before the existing admin upload, compare `s3-cloudfront-deploy` profile `admin-hashed` with `scripts/deploy/deploy-admin-www.sh`. The comparison is `continue-on-error: true`. The upload step stays the script.

## Non-goals

- No switch. The upload is still `bash scripts/deploy/deploy-admin-www.sh`.
- No edit to that script. The workflow wraps `aws` so the comparison's S3 commands are `--dryrun` and its invalidation is skipped.

## Files

`.github/workflows/deploy-admin-web.yml`, `scripts/test_workflow_secrets.py`, `docs/deployment/admin-website.md`, this plan.

## Invariants this change preserves

- The job still runs only on `main`, after the build, with `aws-oidc` and `secrets.AWS_ACCOUNT_ID`.
- The upload step's `run` and `env` stay as they are on `main`.

## Done when

`python3 -m unittest scripts.test_workflow_secrets` passes. After merge, a `main` run prints `Dry run matches the current deploy (N planned S3 changes)` and the script still uploads. Only then does a follow-up replace the script.

## Rollback

Revert the pull request.

## Open questions

None.
