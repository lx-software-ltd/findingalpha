# Plan: Pilot setup-node and setup-python

**Status**: In progress
**Zone**: yellow

Parent plan: [Shared actions repository and CI convergence](https://github.com/lx-software-ltd/actions/blob/c850872471a02a3f6112a9c5321b485e7f181443/docs/plans/shared-actions-and-ci-convergence.md), step SA-301.

## Goal

Call `lx-software-ltd/actions` `setup-node` and `setup-python` at `c850872471a02a3f6112a9c5321b485e7f181443` from the lint, test, lockfile, and security workflows. Pass the versions these workflows use today: Node `lts/*` and Python `3.12`. Move the `require-jobs` pin in lint and test to that same commit.

## Non-goals

No Node 26 switch. No deploy or key-workflow edit. No `v*` tag. No other action pin.

## Files

- `.github/workflows/lint.yml`
- `.github/workflows/test.yml`
- `.github/workflows/check-lockfiles.yml`
- `.github/workflows/security.yml`
- `docs/plans/sa-301-setup-actions.md`

`npm ci` is folded into `setup-node` where the following install step is exactly `npm ci` in the lockfile directory:

- `apps/public_www` in Lint Public Www and Build Public Www
- `apps/admin_web` in Lint Admin Web, Build Admin Web, and Admin Web viewport smoke
- `backend/infrastructure` in Build CDK, Test Infrastructure, and Checkov IaC Security

Check Node.js lockfiles passes only `node-version`. It does not cache and does not install. Its own `npm ci` loop stays.

## Invariants this change preserves

Job names stay. Checkout stays on `actions/checkout@v7`. Later lint, build, test, and Playwright steps stay. Python steps do not pass `requirements`, and the following pip installs stay. The CodeQL Python setup keeps `if: matrix.language == 'python'`. Gate jobs keep `needs`, `if: always()`, the step name, and `needs-json`. No secret is added.

## Done when

The four workflow files contain no `actions/setup-node@v7`, no `actions/setup-python@v7`, and no `1a3cca7`. Every `lx-software-ltd/actions` reference in those files is `c850872471a02a3f6112a9c5321b485e7f181443`.

`github-actions` check-run names on `main` `d924cc4b1bdee7477b49b3352eccd7a4762639ea`:

- Check Node.js lockfiles
- Checkov IaC Security
- CodeQL Analysis (javascript)
- CodeQL Analysis (python)
- PII denylist
- Secret Scanning
- Security Summary
- Semgrep SAST

This pull request must keep those names. Checkov, CodeQL, and Semgrep OSS from `github-advanced-security` may appear only on the pull request.

## Rollback

Revert the pull request. The `@v7` setup steps and the `1a3cca7` gate pin return.

## Open questions

None.
