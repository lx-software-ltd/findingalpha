# Plan: mypy on the Python lint job

**Status**: Draft
**Zone**: yellow

## Goal

The Python lint job runs `mypy==1.8.0` on the paths Ruff already checks, and the job fails when mypy reports an error.

## What was wrong

One mypy process on `backend/lambda` stops at the first duplicate module named `handler`. The gate runs one process per top-level directory. That command reported 122 errors (engine 114, public API authorizer 5, scripts 3). Those errors are fixed in the code. The job fails on any remaining error.

## Non-goals

A coverage floor. OpenAPI lint. This repository has no OpenAPI file.

## Files

`.github/workflows/lint.yml`, the Python modules and tests named by mypy, and this plan.

## Invariants this change preserves

The `lint` job id and its display name stay `lint`. The actions pin stays `ffde04dca3c78b1ccb8739f4d3a23f728ac7a05f`. mypy still uses `--ignore-missing-imports`. A mypy exit code other than 0 fails the job.

## Done when

`mypy 1.8.0 --ignore-missing-imports` exits 0 in `backend/lambda/engine`, `backend/lambda/public_api_authorizer`, `backend/lambda/pre_token_generation`, `scripts`, and `.cursor/hooks`, and the Mypy step is in `lint-python`.

## Rollback

Revert this pull request.

## Open questions

None.
