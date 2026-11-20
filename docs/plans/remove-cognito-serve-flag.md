# Plan: Remove CognitoServeCustomDomain

**Status**: Ready
**Zone**: red (`backend/infrastructure/**`, `.github/workflows/deploy-*.yml`)

## Goal

When both Cognito custom-domain parameters are set, always serve Hosted
UI on that custom domain. Drop `ADMIN_COGNITO_SERVE_CUSTOM_DOMAIN` /
`CognitoServeCustomDomain`. Pass the admin CSP Cognito origin from
Deploy Backend (same rule as `CognitoDomain`) so clearing the two vars
cannot leave an export lock on `findingalpha-admin-web`.

## Non-goals

- Restoring prefix-domain deletion.
- Restoring a serve flag or a two-phase cutover.
- Putting hostnames or certificate ARNs in git.

## Files

- `backend/infrastructure/lib/constructs/auth.ts`
- `backend/infrastructure/lib/parameters.ts`
- `backend/infrastructure/lib/findingalpha-stack.ts`
- `backend/infrastructure/lib/findingalpha-admin-web-stack.ts`
- `backend/infrastructure/bin/app.ts`
- `.github/workflows/deploy-backend.yml`
- tests, docs, `contracts/roadmap.json` (O22)

## Invariants this change preserves

- Prefix domain always remains alongside the custom domain.
- Both custom-domain vars or neither; exactly one fails the deploy.
- CSP and `CognitoDomain` use the same inputs (both custom-domain vars).

## Cutover

1. Add the Google redirect URI for `https://auth.<domain>/oauth2/idpresponse`.
2. Set both custom-domain variables and deploy. The SPA switches on that
   deploy.
3. If the `auth` DNS CNAME is not already live, sign-in is down until it
   points at `CognitoCustomDomainTarget`.

## Done when

- `npm test` and `npm run build` in `backend/infrastructure` pass.
- Workflow and contract checks pass.
- Admin-web template has no `Fn::ImportValue` of `findingalpha-CognitoDomain`.

## Rollback

Clear both `ADMIN_COGNITO_CUSTOM_DOMAIN_*` variables and redeploy. The
prefix domain was never deleted; CSP is a parameter from those same
vars, so the admin-web stack does not hold an export of `CognitoDomain`.

## Open questions

None.
