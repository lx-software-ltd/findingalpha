# Plan: Bandit marks on application asserts

**Status**: In progress
**Zone**: yellow

## Goal

Keep the seven application asserts Bandit still reports after test files
are excluded. Each line is a type narrowing after a None check, and it
carries `# nosec B101`.

## Non-goals

- No skip list on the Bandit action.
- No `# nosec` on test files. Tests next to the Lambda code are excluded
  by the workflow input `**/test_*.py`.

## Files

- `backend/lambda/engine/composite.py`
- `backend/lambda/engine/factors_quality.py`
- `backend/lambda/engine/fundamentals_pit.py`
- `backend/lambda/engine/http_client.py`

## Invariants this change preserves

The asserts stay. The comment only tells Bandit the line was reviewed.

## Done when

`bandit -r backend/lambda -x '**/test_*.py'` exits 0.

## Rollback

Remove the seven comments. The security job fails again on these asserts.

## Open questions

None.
