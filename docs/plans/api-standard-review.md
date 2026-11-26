# Plan: API standard review remediation

**Status**: Draft
**Zone**: yellow

The authorizer and the wire-format guard are yellow. `backend/infrastructure/**` is red; this remediation explicitly asks for the execute-api flag and the identity-source stack test. `contracts/**` stays untouched unless a ticker map is unprotected and the guard would otherwise be vacuous.

## Goal

Accept the legacy `x-api-key` token as well as `Authorization: Bearer` on the partner authorizer, keep `GET /v1/partner`, point the admin smoke doc at the route the API serves, guard data-keyed wire maps, and leave the execute-api endpoint enabled.

## Non-goals

- Do not edit `backend/lambda/engine/wire_format.py` or any `wireFormat.ts`.
- Do not change `_require_admin`.
- Do not disable the execute-api endpoint on this branch.
- Do not add a health monitor. Update an existing assertion of the old health body only if one is in this repo.
- Do not rename `GET /v1/partner`.

## Files

- `docs/plans/api-standard-review.md` (this note, removed in the last commit)
- `backend/lambda/public_api_authorizer/handler.py`
- `backend/lambda/public_api_authorizer/test_handler.py`
- `backend/infrastructure/lib/authorizers.ts`
- `backend/infrastructure/lib/http-api.ts`
- `backend/infrastructure/test/findingalpha-stack.test.ts`
- `backend/lambda/engine/test_wire_format.py`
- `docs/deployment/admin-website.md`
- `docs/architecture/security.md`

## Invariants this change preserves

- `_require_admin` is unchanged.
- `GET /v1/partner` stays the index route.
- The authorizer still includes source IP and still caches for 60 seconds. The cache key lists both `Authorization` and `x-api-key`.
- The wire codec bytes are unchanged. Existing wire-format cases still pass.
- `DisableExecuteApiEndpoint` is false, so the execute-api hostname stays on.

## Done when

- Authorizer tests cover bearer and the legacy `x-api-key` header, and a log line carries `auth_scheme` `bearer` or `legacy`.
- The stack test lists both `$request.header.Authorization` and `$request.header.x-api-key`.
- The stack test expects `DisableExecuteApiEndpoint` false.
- `python3 -m unittest discover -s backend/lambda/public_api_authorizer -p 'test_*.py'`
- `python3 -m unittest discover -s backend/lambda/engine -p 'test_wire_format.py' -v`
- `python3 -m ruff check` on the edited Python files
- `npm test` and `npm run build` in `backend/infrastructure`
- The API contract checker reports no findings for `docs/api`.

## Rollback

Revert this branch. The execute-api endpoint stays enabled, so reverting the authorizer returns callers to `Authorization: Bearer` only.

## Open questions

- No monitor, synthetic, or doc in this repo asserts the old health body. The handler already returns `{"status": "ok"}`.
