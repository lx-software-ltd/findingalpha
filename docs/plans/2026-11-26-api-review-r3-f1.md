# Plan: API review round 3, F1

**Status**: Done
**Zone**: yellow, with the two infrastructure lines the review named

## Goal

Deny a DynamoDB `ClientError` from the public API authorizer. Pass the HTTP method into the admin wire-codec route. Return an empty body for a non-JSON 204, 205, or 304. Remove the unused `httpApiEndpoint` field. Keep the execute-api export and note that it goes in the next release after this admin-web stack has deployed.

## Non-goals

The authorizer identity source stays the source IP. The authorizer cache stays at 0 seconds. `wireFormat.ts` and `wire_format.py` stay the shared codec. The execute-api `Fn::If` and the API Description stay for the F2 change.

## Files

- `backend/lambda/public_api_authorizer/handler.py`
- `backend/lambda/public_api_authorizer/test_handler.py`
- `apps/admin_web/src/lib/apiAdminClient.ts`
- `apps/admin_web/src/lib/apiAdminClient.test.ts`
- `backend/infrastructure/lib/findingalpha-stack.ts`
- `backend/infrastructure/lib/app-assembly.ts`

## Invariants this change preserves

A missing or invalid key is still a deny. `ClientError.response` still supplies the error code when the exception is a `ClientError`. `rootMaps` lookup stays `contract.rootMaps[route]`. The admin-web stack can still import the execute-api endpoint.

## Done when

`python3 -m unittest discover -p 'test_*.py' -v` in `backend/lambda/public_api_authorizer` passes. `npm run test:unit` in `apps/admin_web` passes. `npm test` and `npm run build` in `backend/infrastructure` pass. `python3 -m ruff check backend/lambda scripts .cursor/hooks` passes.

## Rollback

Revert this commit.

## Open questions

None.
