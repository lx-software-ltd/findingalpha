# Plan: Keep identifiers out of public logs

**Status**: Approved
**Zone**: red

The owner approved the deploy-workflow change in chat on 15 Nov 2026,
then asked for the review findings on that change to be fixed. The
deploy workflows are red. `cdk-diff.yml` is updated with them.

## Goal

- The account id and the owner emails are GitHub secrets, so a public
  Actions log shows `***` instead of the value. When the secret is
  empty, the workflow uses the variable of the same name and the
  deploy still runs. The first step warns, its settings block shows
  the value, and later lines are masked.
- `cdk-diff` still compares the account on a Dependabot pull request.
  That run receives Dependabot secrets, not Actions secrets, so
  `AWS_ACCOUNT_ID` is set in both stores.
- The diff job summary has the account id removed before it is written.
  The summary is not covered by log masking.
- A deploy runs only from `main`.
- The owner checklist names `AdminWebDistributionDomain` and does not
  store the live CloudFront hostname.

## Non-goals

- No stack or Lambda change.
- No change to which settings are required. An allow-list or bootstrap
  email that is empty as both a secret and a variable still fails the
  deploy.
- Branch protection, the `production` environment's branch limit, and
  deleting runs that already printed the values stay owner tasks.
- The Google client id stays a variable. Sign-in shows it in the
  browser.

## Files

- `.github/workflows/deploy-backend.yml`
- `.github/workflows/deploy-admin-web.yml`
- `.github/workflows/cdk-diff.yml`
- `scripts/test_workflow_secrets.py`
- `docs/plans/owner-checklist.md`, `docs/plans/reference.md`,
  `docs/deployment/setup.md`, `docs/deployment/admin-website.md`

## Invariants this change preserves

- A missing account id, allow-list, or bootstrap email stops the deploy
  before CloudFormation changes.
- `cdk-diff` passes with a warning when the account secret or the
  region variable is unset, and fails on a real `cdk diff` error once
  both are set.
- An unset brief recipient or SEC contact still means empty.

## Done when

- `python3 -m unittest scripts/test_workflow_secrets.py` passes.
- `ruff check`, `check_pii.py`, `check_test_focus.py`, and
  `check_file_length.py` pass.
- The three docs name the Dependabot secret, and the checklist has no
  CloudFront hostname.

## Rollback

Revert the commits. A deploy that runs before the secrets exist fails
and leaves the stacks as they are. The DNS record is independent.

## Open questions

None.
