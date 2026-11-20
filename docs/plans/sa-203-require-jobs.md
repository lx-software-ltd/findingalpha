# Plan: Pin lint and test gates to require-jobs

**Status**: In progress
**Zone**: yellow

Parent plan: Shared actions repository and CI convergence, step SA-203.

## Goal

Replace the inline lint and test gates with `lx-software-ltd/actions/require-jobs` at `1a3cca7c38163f8164c262323601c34a4df5b7a4`.

## Non-goals

No other workflow. No tag. No other repository.

## Files

- `.github/workflows/lint.yml`
- `.github/workflows/test.yml`
- `docs/plans/sa-203-require-jobs.md`

## Invariants this change preserves

Check names stay the same. Gates still fail unless every needed job succeeded. No secret is added.

## Done when

The pull request head's check-run names equal this list, and the jobs named `lint` and `test` succeed.

- Admin Web viewport smoke
- Build Admin Web
- Build CDK
- Build Public Www
- Check Node.js lockfiles
- Checkov IaC Security
- Check shared contracts
- CodeQL Analysis (javascript)
- CodeQL Analysis (python)
- lint
- Lint Admin Web
- Lint Public Www
- Lint Python
- PII denylist
- Secret Scanning
- Security Summary
- Semgrep SAST
- test
- Test Infrastructure
- Test Python
- Validate agent harness

## Rollback

Revert the pull request. The inline steps return.

## Open questions

None.
