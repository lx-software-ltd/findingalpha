# Plan: Switch the public website upload

**Status**: In progress
**Zone**: red

## Goal

Replace the findingalpha public website upload with `s3-cloudfront-deploy` profile `public-hashed`. The dry run on `main` (run 45112489631) printed `Dry run matches the current deploy (9 planned S3 changes)` and the script still uploaded and invalidated.

## Non-goals

- No other site. Admin, lx-software, Amplify, and CDK stay on their own pull requests.
- No change to the bucket or distribution lookup. The job still reads `PublicWebsiteBucketName` and `PublicWebsiteDistributionId`.

## Files

`.github/workflows/deploy-public-website.yml`, `scripts/test_workflow_secrets.py`, `docs/deployment/public-website.md`, this plan.

## Invariants this change preserves

- The job still runs only on `main`, after the build, and only when `findingalpha-public-www` exists.
- Credentials still come from `aws-oidc` with `secrets.AWS_ACCOUNT_ID`.
- `dry-run` is `false`. The action uploads and invalidates.

## Done when

`python3 -m unittest scripts.test_workflow_secrets` passes and workflow conformance passes. After merge, a `main` run uploads with the action.

## Rollback

Revert the pull request. The next `main` run uses `scripts/deploy/deploy-public-website.sh` again.

## Open questions

None.
