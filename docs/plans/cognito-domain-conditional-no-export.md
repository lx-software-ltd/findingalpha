# Plan: Conditional CognitoDomain without export

**Status**: Ready
**Zone**: red (`backend/infrastructure/**`)

## Goal

Restore the `Fn::If` on the `CognitoDomain` stack output (custom Hosted
UI URL when both custom-domain params are set, otherwise the prefix).
Drop `exportName` on that output so nothing can reintroduce an export
lock; Deploy Admin Web already reads it via describe-stacks.

## Non-goals

- Changing CSP dual-origin derivation in Deploy Backend.
- Reintroducing a serve flag or CognitoDomain import into admin-web.

## Files

- `backend/infrastructure/lib/constructs/auth.ts`
- `backend/infrastructure/lib/outputs.ts`
- tests and docs / O22

## Done when

- `CognitoDomain` Value contains `Fn::If` on `AuthUseCustomAuthDomain`.
- `CognitoDomain` has no `Export` in the template.
- `npm test` / `npm run build` in `backend/infrastructure` pass.

## Rollback

Revert this PR.
