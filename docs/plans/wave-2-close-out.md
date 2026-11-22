# Plan: Wave 2 close-out

**Status**: Draft
**Zone**: yellow

## Goal

Move `findingalpha` onto the wave 1 actions commit and close the CI convergence rows that apply here. `workflow-conformance` stays in warn until the last commit of this pull request, which switches it to enforce.

## Non-goals

Part B. No deploy, bootstrap, or key-management workflow is triggered. C28's Dependabot exclude for `lx-software-ltd/actions` is not set, because that option is not measured. C23, C24, and C25 stay for Stage 5.

## Files

`.github/workflows/`, `.github/dependabot.yml`, `.pre-commit-config.yaml`, `.cursor/hooks/stop_gate.py`, `.cursor/rules/00-repository-core.mdc`, `.cursor/skills/verify-change/SKILL.md`, `docs/architecture/zones.md`, and the deleted local hook scripts.

## Invariants this change preserves

- One `lx-software-ltd/actions` commit: `61b67ed4f686659433f6ca4cb10c80707e365cd0`.
- The pre-commit `rev` is that same commit.
- `lint` and `test` stay the required check names.
- The PII denylist file stays. The hook reads it. No plaintext was added.
- Deploy workflows are not triggered. Their account-id expressions are unchanged.

## Done when

- `workflow-conformance` in enforce mode reports no findings.
- Bandit on `backend/lambda`, with the recorded skips, exits 0. Measured 22 Nov 2026: no high or medium findings. Skipped tests are B101 (asserts), B105 and B106 (secret names and test fixtures), and B311 (a seeded `Random` in a unit test). `scripts/probe_data_sources.py` stays out of CI, as its own docstring says.
- `npm audit --omit=dev --audit-level=high` reports no high advisory. `backend/infrastructure` has a moderate `minimatch` advisory below that level.
- `pip-audit` could not run on this machine because `python3-venv` is missing. The requirements files contain only pinned `boto3` and `botocore`, and an empty authorizer file. CI is the first complete run.
- Python requirement pins pass.
- The agent harness check passes after the core-rule sentence change.
- `python3 -m unittest scripts/test_agent_hooks.py` passes.

## Rollback

Revert this pull request. The previous pin is `aab84b76383d5a44838f9617ac47b23cfff7fdaf`.

## Open questions

The owner dismisses CodeQL alerts that stay open under the old `javascript` category (C12).
