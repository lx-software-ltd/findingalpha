# Plan: Name the dependency workflow Dependency Submission

**Status**: Done
**Zone**: green

## Goal

The Actions tab uses title case, and GitHub's built-in "Dependency Graph" entry sits next to ours, so this workflow must not use that name.

`.github/workflows/dependency-graph.yml` is not on the red list (red deploy workflows are `deploy-*.yml`) and is not on the yellow path list. `docs/**` is green. The zone for this change is green. The task still requires this plan file.

## Non-goals

Leave file names, job ids, pins, comments, and every other line alone. Do not add tests. Do not rename "Deploy iOS". Do not add a Sync Labels workflow. Do not edit `.pre-commit-config.yaml`.

## Files

- `.github/workflows/dependency-graph.yml` — workflow `name:` and the two job `name:` display strings
- `docs/plans/2026-11-24-dependency-submission-name.md` — this plan

## Invariants this change preserves

- Job ids stay `check` and `submit`.
- Step names stay as they are.
- This pull request does not edit the pin. main already has `lx-software-ltd/actions/dependency-graph@48ffe6dadb6c1540b8992e8e8edfda4f8aa0933e # main 2026-11-24` from #103. Checkout pins stay unchanged.
- Triggers, permissions, `if` conditions, and `runs-on` stay unchanged.

## Done when

- Workflow `name:` is `Dependency Submission`.
- Job `check` `name:` is `Check Dependency Submission`.
- Job `submit` `name:` is `Submit Dependency Submission`.
- Workflow conformance at the pinned actions commit prints `Workflow conformance passed.`
- `python3 scripts/test_workflow_secrets.py` passes.

## Rollback

Revert the pull request. The three display strings return to `Dependency graph`, `Check dependency graph`, and `Submit dependency graph`, and this plan file goes with them.

## Open questions

None.
