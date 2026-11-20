# Plan: Copy the organisation PII denylist

**Status**: In progress
**Zone**: red

Parent plan: Shared actions repository and CI convergence, in
`lx-software-ltd/actions` `docs/plans/shared-actions-and-ci-convergence.md`.

The owner approved gate G2 for `scripts/pii-denylist.sha256` only, in
chat on 20 Nov 2026. Pre-commit, hooks, and the PII scripts are not
part of this change.

## Goal

The denylist holds the 31 digests shared by `evolvesprouts` and
`siutindei`, so the PII job checks this repository against the
organisation list.

## Non-goals

- No plaintext, and no digest invented in this repository.
- No change to `scripts/check_pii.py` or `scripts/check-pii.sh`.
- No workflow edit.
- No edit to pre-commit or Cursor hooks.

## Files

- `scripts/pii-denylist.sha256`
- `docs/plans/owner-checklist.md` (O03)
- `docs/plans/g2-pii-denylist.md`

## Invariants this change preserves

- The file contains digests and comments only.
- A hit is a path and a line number, never the matched text.
- Check names do not change. `lint` and `test` stay required.

## Done when

`python3 scripts/check_pii.py` passes. `python3 -m unittest scripts/test_check_pii.py` passes.

Check names on `main` (`8c3d3aaf2260966242e600b262d5ce876785272f`). That
commit only changed workflow permissions, and `push` is path-filtered,
so the API returned the security workflow only:

- Check Node.js lockfiles
- Checkov IaC Security
- CodeQL Analysis (javascript)
- CodeQL Analysis (python)
- PII denylist
- Secret Scanning
- Security Summary
- Semgrep SAST

This pull request does not add or remove a job, so the pull request's
own `lint` and `test` runs are the evidence those names still report.

## Rollback

Revert this pull request. The denylist returns to a comment, and the
PII job checks nothing again.
