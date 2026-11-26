# Plan: one API standard

**Status**: In progress
**Zone**: red for `backend/infrastructure/**` and `contracts/**`. Yellow for the Lambda handlers, the authorizer and the admin site. The owner approved those red paths in the kickoff for this plan, and no others.

## Goal

Serve `https://api.findingalpha.app/v1/<audience>/<resource>` with bearer tokens, snake_case JSON at the HTTP boundary, one error shape, and one OpenAPI file per audience.

The rules and the steps are in [`lx-software-ltd/actions` `docs/plans/api-standard.md` at `dadcbf4`](https://github.com/lx-software-ltd/actions/blob/dadcbf4d63519cb93117f85925b6f90e013e057b/docs/plans/api-standard.md). This pull request is work package F1.

## Non-goals

Scope names, token expiry, idempotency keys, and making `next_cursor` the only page field. No deploy from this pull request.

## Files

- `backend/infrastructure/**` routes, authorizer identity source, CORS, `AdminApiBaseUrl`, `DisableExecuteApiEndpoint`
- `backend/lambda/public_api_authorizer/` reads `Authorization`
- `backend/lambda/engine/` audience split, errors, request id, wire codec
- `contracts/wire-format.json` and `contracts/wire-format-cases.json`
- `apps/admin_web/src/lib/wireFormat.ts` and the admin paths
- `docs/api/admin.yaml`, `docs/api/partner.yaml`
- `.github/workflows/lint.yml` OpenAPI job

## Invariants this change preserves

- `_require_admin` is not edited. A JWT route still requires the admin group.
- Storage keys stay camelCase. Only the HTTP boundary renames keys.
- The key authorizer still denies on any error and does not decide by HTTP method.
- No secret, account id or `execute-api` hostname is added to a file.

## Done when

`npm test` in `backend/infrastructure`, the Python tests, the admin site's `npm test`, `python3 scripts/check-contracts.py`, the Redocly lint and the route comparison pass.

## Rollback

Revert the merge commit and deploy. Paths, the header and the field names move back together.

## Open questions

None for this repository.
