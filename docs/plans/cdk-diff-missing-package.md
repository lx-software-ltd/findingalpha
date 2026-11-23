# Plan: CDK Diff warns when the app is missing

**Status**: Merged in findingalpha #85 (`04b14ed`).
**Zone**: yellow

## Goal

The CDK Diff install step and the preparation step already succeed when `backend/infrastructure/package.json` is missing. They now also emit `::warning::`, so a green run is not silent. The preparation step still sets `run=false` and does not run the diff.

## Non-goals

- No pin change. Every `lx-software-ltd/actions` use stays on `12ce7549f74db10a3c595214bf411deba0ef728a`.
- No deploy or promote edit. That is SA-503.
- The step still exits 0. A missing app is a skip, not a failed diff.

## Files

`.github/workflows/cdk-diff.yml`

## Invariants this change preserves

- `run=false` when the app is missing, and the diff step does not run.
- The account id stays a secret. This change does not print it.
- One actions SHA, with a `# main YYYY-MM-DD` comment.

## Done when

`CONFORMANCE_ROOT` for this repository, `CONFORMANCE_MODE=enforce`, and `CONFORMANCE_PROFILE=product` pass.

## Rollback

Revert this pull request.
