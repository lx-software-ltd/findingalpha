# Plan: Refresh the Semgrep category the open alerts use

**Status**: Done
**Zone**: red

## Goal

The open Semgrep alerts stay visible because the scan uploads `semgrep` from `semgrep.yml`. They were filed under `.github/workflows/security.yml:semgrep`. Pin the Semgrep action that uploads both categories.

## Non-goals

The secret-store log and the probe URL check stay as they are.

## Files

Every `lx-software-ltd/actions` pin, `.pre-commit-config.yaml`, and `scripts/test_lighthouse_workflow.py`.

## Invariants this change preserves

Workflow text other than the pin stays the same. One pin is used everywhere.

## Done when

`python3 -m unittest scripts/test_lighthouse_workflow.py` passes. Workflow conformance against the pinned actions checkout passes.

## Rollback

Restore the previous pin and the pre-commit rev.

## Open questions

None.
