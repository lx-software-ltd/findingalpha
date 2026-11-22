# Plan: Pilot cdk-bootstrap-check and cdk-diff

**Status**: In progress
**Zone**: red

`.pre-commit-config.yaml` is red. This pull request changes only its `rev`, because workflow conformance allows one `lx-software-ltd/actions` commit and that rev has to be the same commit. `cdk-diff.yml` is yellow. SA-502 was started in chat. No deploy workflow changes.

## Goal

Call `cdk-bootstrap-check` and `cdk-diff` from `cdk-diff.yml`. The bootstrap check reads the SSM version and does not bootstrap. The diff action masks the account id and writes the step summary. Parameter loading, the default stack names, `cdk acknowledge`, and `npm run build` stay in this workflow. The account id is `secrets.AWS_ACCOUNT_ID` only. The pin is `12ce7549f74db10a3c595214bf411deba0ef728a`, the merge commit of actions#32, with a `# main 2026-11-22` comment.

## Non-goals

- No deploy, promote, or key-management workflow. That is SA-503.
- No change to the pull-request paths or `workflow_dispatch`.
- No second actions commit. Every shared-action pin and the pre-commit rev move together.
- No account id in git.

## Files

`.github/workflows/cdk-diff.yml`, the other workflow pins, `.pre-commit-config.yaml`, `scripts/test_workflow_secrets.py`, this plan.

## Invariants this change preserves

- The job id stays `diff`.
- A missing account or region does not fail the job.
- An empty stack input still diffs `findingalpha-public-www`, `findingalpha`, and `findingalpha-admin-web`.
- The CDK app still receives `CDK_BOOTSTRAP_QUALIFIER` from the job environment.
- Deploy workflows still mask the account id themselves.

## Done when

`python3 -m unittest scripts/test_workflow_secrets.py` passes. Workflow conformance in enforce mode reports one actions commit.

## Rollback

Revert this pull request. The previous pin is `839efa2c91be72e748867031dc6b285011fbf627`.

## Open questions

None.
