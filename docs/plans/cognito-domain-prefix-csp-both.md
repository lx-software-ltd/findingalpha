# Plan: CognitoDomain stays on prefix; CSP allows both

**Status**: Ready
**Zone**: red (`backend/infrastructure/**`, `.github/workflows/deploy-*.yml`)

## Goal

Keep the `CognitoDomain` stack output on the Cognito prefix URL always.
When the custom domain is configured, pass both the prefix origin and
`https://auth.<domain>` in `CspCognitoConnectOrigin` (space-separated).

## Non-goals

- Switching the SPA to `auth.<domain>`.
- Restoring a serve flag or CognitoDomain export import into admin-web.

## Files

- `backend/infrastructure/lib/constructs/auth.ts`
- `.github/workflows/deploy-backend.yml`
- tests and docs / O22

## Done when

- `CognitoDomain` template value is the prefix `Fn::Join` only (no `Fn::If`).
- Workflow sets CSP to prefix, or `prefix https://auth.<domain>` when both
  custom-domain vars are set.
- `npm test` / `npm run build` and workflow secrets tests pass.

## Rollback

Revert this PR.
