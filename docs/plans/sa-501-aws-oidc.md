# Plan: Pilot aws-oidc in CDK diff

**Status**: In progress
**Zone**: red

`.pre-commit-config.yaml` is red. This pull request changes only its `rev`, because workflow conformance allows one `lx-software-ltd/actions` commit and that rev has to be the same commit. SA-501 was started in chat. No deploy workflow changes.

## Goal

Call `aws-oidc` from `cdk-diff.yml`. The account id is still `secrets.AWS_ACCOUNT_ID || vars.AWS_ACCOUNT_ID`. The subject is the ID form `repo:lx-software-ltd@321652495/findingalpha@1456774357:*`. `required` stays false, so a missing account or region warns and skips the diff.

## Non-goals

- No deploy, promote, or key-management workflow. That is SA-503.
- No second actions commit. Every shared-action pin and the pre-commit rev move together.
- No account id in git.

## Files

`.github/workflows/cdk-diff.yml`, the other workflow pins, `.pre-commit-config.yaml`, `scripts/test_workflow_secrets.py`, this plan.

## Invariants this change preserves

- The job id stays `diff`.
- The diff still strips the account id from the step summary.
- A missing account or region does not fail the job.
- Deploy workflows still mask the account id themselves.

## Done when

`python3 -m unittest scripts/test_workflow_secrets.py` passes. Workflow conformance in enforce mode reports one actions commit.

## Rollback

Revert this pull request. The previous pin is `9235676200771b2f93bc01ac85f3de1392133182`.

## Open questions

None.
