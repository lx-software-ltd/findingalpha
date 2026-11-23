# Plan: mypy error ceiling

**Status**: Draft
**Zone**: yellow

## Goal

The Python lint job fails when `mypy==1.8.0` reports more than 122 errors on the paths Ruff already checks. The 122 existing errors stay allowed.

## Non-goals

Driving the count to zero. A coverage floor. OpenAPI lint. This repository has no OpenAPI file.

## Measurement

`mypy 1.8.0 --ignore-missing-imports`, one process per directory. One process on `backend/lambda` stops at the first duplicate module named `handler` and does not reach the other errors.

| Directory | Errors |
| --- | --- |
| `backend/lambda/engine` | 114 |
| `backend/lambda/public_api_authorizer` | 5 |
| `backend/lambda/pre_token_generation` | 0 |
| `scripts` | 3 |
| `.cursor/hooks` | 0 |
| Total | 122 |

The same total is on `75df15d` and on current `main`. An earlier note of 119 is not what this command prints, so the ceiling is 122.

## Files

`.github/workflows/lint.yml` and this plan.

## Invariants this change preserves

The `lint` job id and its display name stay `lint`. The actions pin stays `ffde04dca3c78b1ccb8739f4d3a23f728ac7a05f`. A mypy exit code above 1 still fails the job.

## Done when

The Mypy step is in `lint-python`, and that command prints `mypy errors: 122 (ceiling 122)`.

## Rollback

Revert this pull request.

## Open questions

None.
