# Plan: Fail closed on storage errors and make CDK Diff honest

**Status**: Approved
**Zone**: red

The owner approved this plan in chat. It touches `kill_switch.py` and
`backend/infrastructure/**`, which are red, and other engine files,
which are yellow.

## Goal

- A kill switch is off when its settings row cannot be read for any
  storage reason: an AWS error, a client-side boto error, or a missing
  table variable.
- An audit write or a job-run write that fails for the same reasons
  logs a warning and does not fail the request or the job.
- While the account variables are unset, `cdk-diff` passes with a
  warning and does not compare the account. Once they are set, it
  shows the diff in the job summary and fails on a real error. The
  setup docs say so.

## Non-goals

- No change to which jobs have kill switches, or to the settings row.
- No new AWS permissions and no stack resource changes.
- No posting of the diff as a pull request comment. That needs a write
  token on pull requests.

## Files

- `backend/lambda/engine/config.py`: `MissingSetting`, raised for a
  missing table variable. It subclasses `KeyError`, so callers that
  catch `KeyError` still do.
- `backend/lambda/engine/storage_errors.py`: `STORAGE_ERRORS` and
  `error_code`, shared by the three callers below.
- `backend/lambda/engine/kill_switch.py`, `audit.py`, `job_runs.py`:
  catch `STORAGE_ERRORS`.
- Tests: `test_kill_switch.py`, `test_audit.py`, `test_job_runs.py`,
  `test_runtime.py`, `test_storage_errors.py`.
- `.github/workflows/cdk-diff.yml`: no account id in the summary, the
  diff in the summary.
- `docs/deployment/setup.md`, `docs/plans/owner-checklist.md`,
  `docs/plans/reference.md`: the check warns and skips the comparison
  until the variables exist.

## Invariants this change preserves

- Kill switches fail closed.
- A job still records `running`, then `succeeded`, `failed`, or
  `skipped_disabled`.
- An error in a job handler is still recorded and re-raised.
- `cdk diff` keeps its exit code. Exit 0 is success, with or without a
  difference.

## Done when

- `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
  passes with every AWS variable unset.
- With no region and no table variables, `kill_switch.is_enabled`
  returns false, and `audit.write` and `job_runs.record` do not raise.
- `ruff check`, `ruff format --check`, `check_file_length.py`,
  `check_pii.py`, `check_test_focus.py` and `check-contracts.py` pass.
- On the pull request, every check passes. While the account variables
  are unset, `diff` passes with a warning that names them.

## Rollback

Revert the commits. No data or stack state changes.

## Open questions

None.
