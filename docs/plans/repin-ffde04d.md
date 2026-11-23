# Plan: Re-pin the shared actions

**Status**: In progress
**Zone**: yellow

## Goal

Move every `lx-software-ltd/actions` pin and the pre-commit `rev` from `e6be2629d7206b0d5c079662f364772bc816acc1` to `ffde04dca3c78b1ccb8739f4d3a23f728ac7a05f`. That is the commit the other three repositories already use. The comment stays `# main 2026-11-23`.

## Non-goals

- No workflow behaviour change in this pull request. The public and admin uploads and Deploy Backend stay on the actions they already call.
- No edit to an older plan that records the previous pin.

## Files

`.github/workflows/*`, `.pre-commit-config.yaml`, `scripts/test_workflow_secrets.py`, `docs/deployment/public-website.md`, this plan.

## Invariants this change preserves

- One actions commit for the whole repository.
- Callers still pass `secrets.AWS_ACCOUNT_ID` only.

## Done when

`python3 -m unittest scripts.test_workflow_secrets` passes and workflow conformance passes.

## Rollback

Revert the pull request.

## Open questions

None.
