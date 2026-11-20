# Plan: Cognito custom Hosted UI on auth.<domain>

**Status**: Replaced
**Zone**: red (`backend/infrastructure/**`, `.github/workflows/deploy-*.yml`)

This plan is historical. The serve-flag cutover it described was removed.
Follow [`remove-cognito-serve-flag.md`](remove-cognito-serve-flag.md).

## Original goal (kept)

Enable the Cognito Hosted UI on `auth.<domain>` via GitHub environment
variables like `api.<domain>`, and keep the Cognito prefix domain so
both can coexist.

## What changed later

- `ADMIN_COGNITO_SERVE_CUSTOM_DOMAIN` was removed; when both custom-domain
  vars are set, `CognitoDomain` always uses the custom hostname.
- Admin CSP no longer imports `findingalpha-CognitoDomain`; Deploy Backend
  passes `CspCognitoConnectOrigin` from the same variables.
