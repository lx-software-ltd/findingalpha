# Plan: One actions SHA

**Status**: In progress
**Zone**: yellow

A pull request is opened.

## Goal

Replace every `lx-software-ltd/actions` pin that is not already `61d2a581a1d880533982bada88923ad1b6431700` with that SHA. The comment stays `# main 2026-11-20`.

On main those pins are `c850872471a02a3f6112a9c5321b485e7f181443` in the CI workflows (`require-jobs`, `setup-node`, `setup-python`). `61d2a581a1d880533982bada88923ad1b6431700` contains those actions unchanged plus `verify-rulesets`.

After this pull request and #74 both merge, every `lx-software-ltd/actions` reference is `61d2a581a1d880533982bada88923ad1b6431700`.

## Non-goals

No change to inputs, runners, job `needs`, or checkout lines. No edit to `deploy-*.yml`, `cdk-diff.yml`, or `manage-api-keys.yml`. No new `verify-rulesets` call. #74 already calls that action at this same SHA.

## Files

- `.github/workflows/lint.yml`
- `.github/workflows/test.yml`
- `.github/workflows/check-lockfiles.yml`
- `.github/workflows/security.yml`
- `docs/plans/one-actions-sha.md`

## Invariants this change preserves

Action inputs stay. Runners stay. Job `needs` stay. Checkout lines stay `actions/checkout@v7`. The pin comment stays `# main 2026-11-20`. `verify-rulesets.yml` stays on the SHA it already uses.

## Done when

`lint.yml`, `test.yml`, `check-lockfiles.yml`, and `security.yml` contain no `c850872` and no `1a3cca7`. Every `lx-software-ltd/actions` pin in those files is `61d2a581a1d880533982bada88923ad1b6431700` with the comment `# main 2026-11-20`.

## Rollback

Revert the pull request.

## Open questions

None.
