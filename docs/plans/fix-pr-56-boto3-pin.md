# Plan: Accept boto3 1.44.4 and clear Dependabot label errors

**Status**: Ready
**Zone**: yellow

## Goal

Make Dependabot's boto3/botocore 1.44.4 bump pass CI, and stop
Dependabot from asking for labels that do not exist on the repository.

PR 56 updates `backend/lambda/engine/requirements.txt` to
`boto3==1.44.4` and `botocore==1.44.4`. The pin test still expects
1.44.3, so Test Python fails. The Build Admin Web job runs the same
engine suite and fails for the same reason. Dependabot also comments
that labels `dependencies` and `lambda` are missing.

## Non-goals

- Re-checking managed knowledge base shapes against a live account.
  1.44.4 is a patch release on the same 1.44 line already accepted in
  M07; the floor remains botocore >= 1.43.64.
- Creating GitHub labels through the API. Labels are removed from
  `dependabot.yml` instead, because the agent cannot create them.

## Files

- `backend/lambda/engine/test_boto3_pin.py`
- `backend/lambda/engine/requirements.txt` (comments only; pins already
  on the Dependabot commit)
- `.github/dependabot.yml`
- `docs/plans/fix-pr-56-boto3-pin.md` (this plan)

## Invariants this change preserves

- `AdminApiFn` and `EngineFn` still bundle an exact boto3/botocore pair
  from the engine requirements file.
- The pin test still asserts the full requirements list, so a drift
  between the two pins still fails CI.
- Dependabot still watches the same ecosystems and directories.

## Done when

- `python3 -m unittest discover -s backend/lambda/engine -p 'test_boto3_pin.py' -v`
- `python3 -m ruff check backend/lambda/engine/test_boto3_pin.py`
- `python3 scripts/check_pii.py`

## Rollback

Restore the pin test and comments to 1.44.3, restore the Dependabot
label lists, and close or revert the bump.

## Open questions

None.
