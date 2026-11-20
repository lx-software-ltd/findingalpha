# Plan: Cognito custom Hosted UI on auth.<domain>

**Status**: Ready
**Zone**: red (`backend/infrastructure/**`, `.github/workflows/deploy-*.yml`)

## Goal

Enable the Cognito Hosted UI on `auth.<domain>` without a sign-in
outage, pass hostname and certificate through GitHub environment
variables like `api.<domain>`, and keep the admin CSP Cognito origin in
step with the `CognitoDomain` stack output.

## Non-goals

- Putting the domain or certificate ARN in git.
- Deleting the Cognito prefix domain (AWS allows both; keeping the
  prefix avoids downtime and makes rollback safe).
- A separate `ADMIN_COGNITO_ORIGIN` variable for CSP.

## Cutover

1. Set `ADMIN_COGNITO_CUSTOM_DOMAIN_NAME` and
   `ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN`. Leave
   `ADMIN_COGNITO_SERVE_CUSTOM_DOMAIN` unset or `false`.
2. Deploy Backend. Cognito creates the custom domain; the prefix domain
   stays; `CognitoDomain` (and CSP) still use the prefix.
3. Confirm the parent `<domain>` resolves (Cognito requires it). Add the
   `auth` CNAME to `CognitoCustomDomainTarget` after the owner says go.
   Add `https://auth.<domain>/oauth2/idpresponse` to the Google client.
4. Set `ADMIN_COGNITO_SERVE_CUSTOM_DOMAIN=true` and redeploy. The SPA
   and CSP switch to `https://auth.<domain>`.

## Rollback

Set `ADMIN_COGNITO_SERVE_CUSTOM_DOMAIN=false` (or unset it) and redeploy
so `CognitoDomain` returns to the prefix. Optionally clear the two
custom-domain variables on a later deploy to remove the custom domain
resource. The prefix domain was never deleted.

## Files

- `.github/workflows/deploy-backend.yml`
- `backend/infrastructure/lib/constructs/auth.ts`
- `backend/infrastructure/lib/parameters.ts`
- `backend/infrastructure/lib/findingalpha-stack.ts`
- `backend/infrastructure/lib/findingalpha-admin-web-stack.ts`
- `backend/infrastructure/bin/app.ts`
- tests under `backend/infrastructure/test/` and `scripts/test_workflow_secrets.py`
- `contracts/roadmap.json` (O22) and docs

## Invariants this change preserves

- Empty name or empty certificate keeps only the Cognito prefix domain.
- Domain hostnames and certificate ARNs stay out of git.
- Deploy Admin Web still reads `CognitoDomain` from the stack output.

## Done when

- `npm test` and `npm run build` in `backend/infrastructure` pass.
- `python3 -m unittest scripts.test_workflow_secrets` still passes.
- `python3 scripts/sync-contracts.py` and `check-contracts.py` pass.
- Owner can complete the cutover steps without a sign-in outage.

## Open questions

None. AWS docs confirm a pool may have both a prefix domain and a
custom domain at once.
