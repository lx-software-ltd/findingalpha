# Plan: Wave 2 close-out

**Status**: Draft
**Zone**: yellow

## Goal

Move `findingalpha` onto the wave 1 actions commit and close the CI convergence rows that apply here. `workflow-conformance` is in enforce.

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
- Code scanning categories stay the strings the existing alerts use. CodeQL still analyzes `javascript-typescript` and uploads `/language:javascript`. Python stays `/language:python`. Semgrep uploads `.github/workflows/security.yml:semgrep`.
- Semgrep runs `mode: scan`, which reads the whole repository on a pull request. The previous `semgrep ci` command scanned only files changed since the base. The packs are `p/python`, `p/javascript`, `p/security-audit`, `p/secrets`, and `p/owasp-top-ten`. The two added packs are `p/python` and `p/owasp-top-ten`.
- Bandit on `backend/lambda` exits 0 with skips `B101,B311`. B101 is assert used as type narrowing. B311 is a seeded `Random` in a unit test. B105 and B106 are `# nosec` on the lines that match: the Secrets Manager name, two empty pagination cursors, and the test fixtures. `scripts/probe_data_sources.py` stays out of CI, as its own docstring says.
- `npm audit --omit=dev --audit-level=high` reports no high advisory. `backend/infrastructure` has a moderate `minimatch` advisory below that level.
- The Dependency audit job, which runs `pip-audit`, passed on this pull request. A local run still cannot create a virtualenv because `python3-venv` is missing. That local gap is closed by the CI result.
- Python requirement pins pass.
- The agent harness check passes after the core-rule sentence change.
- `python3 -m unittest scripts/test_agent_hooks.py` passes. A machine without `pre-commit` on `PATH` gets a follow-up from the stop hook. The first `pre-commit` run needs network to clone `lx-software-ltd/actions`.
- Third-party pin comments name the tag whose object is that SHA: `actions/setup-node` and `actions/setup-python` are v7.1.0, `aws-actions/configure-aws-credentials` is v6.3.0, and `docker/setup-qemu-action` is v4.4.0.

## Rollback

Revert this pull request. The previous pin is `aab84b76383d5a44838f9617ac47b23cfff7fdaf`.

## Open questions

None. The CodeQL and Semgrep upload categories were kept, so the existing alerts stay attached.
