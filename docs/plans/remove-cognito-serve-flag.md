# Plan: Remove CognitoServeCustomDomain

**Status**: Ready
**Zone**: red (`backend/infrastructure/**`, `.github/workflows/deploy-*.yml`)

## Goal

When both Cognito custom-domain parameters are set, always serve Hosted
UI on that custom domain. Drop `ADMIN_COGNITO_SERVE_CUSTOM_DOMAIN` /
`CognitoServeCustomDomain`.

## Non-goals

- Restoring prefix-domain deletion.
- Putting hostnames or certificate ARNs in git.

## Files

- `backend/infrastructure/lib/constructs/auth.ts`
- `backend/infrastructure/lib/parameters.ts`
- `backend/infrastructure/lib/findingalpha-stack.ts`
- `.github/workflows/deploy-backend.yml`
- tests, docs, `contracts/roadmap.json` (O22)

## Invariants this change preserves

- Prefix domain always remains alongside the custom domain.
- Both custom-domain vars or neither; exactly one fails the deploy.
- CSP still imports `findingalpha-CognitoDomain`.

## Done when

- `npm test` and `npm run build` in `backend/infrastructure` pass.
- Workflow and contract checks pass.
- No remaining `CognitoServeCustomDomain` / `ADMIN_COGNITO_SERVE_*` refs
  except historical plans that note the removal.

## Rollback

Revert this PR. Redeploy with `ADMIN_COGNITO_SERVE_CUSTOM_DOMAIN` if
needed.

## Open questions

None.
