# Plan: manage-api-keys uses aws-oidc

**Status**: In progress
**Zone**: red

`manage-api-keys.yml` assumes `GitHubActionsRole`. The pre-commit rev does not change. No workflow is dispatched.

## Goal

Replace the account check and `configure-aws-credentials` with `aws-oidc`. The account id is `secrets.AWS_ACCOUNT_ID` only. After this merges, the `AWS_ACCOUNT_ID` variable is not read and can be deleted.

## Non-goals

- No pin change. The action pin stays `c210c3223782894251ba37b4fc71a0c245619d39`.
- No change to key creation, listing, or revocation.
- The role is still assumed before `pip install`, which is where the old credentials step was.
- No workflow run.

## Files

`.github/workflows/manage-api-keys.yml`, `scripts/test_workflow_secrets.py`, `scripts/test_manage_public_api_keys.py`, `docs/plans/owner-checklist.md`, this plan.

## Invariants this change preserves

- The job stays `workflow_dispatch`, production, with `id-token: write`.
- `AWS_REGION` stays a variable.
- A missing passphrase still refuses to create a key.
- The account id is not written into git.

## Done when

`python3 -m unittest scripts/test_workflow_secrets.py` passes. Workflow conformance in enforce mode reports one actions commit. No workflow contains `vars.AWS_ACCOUNT_ID`.

## Rollback

Revert this pull request.

## Open questions

None.
