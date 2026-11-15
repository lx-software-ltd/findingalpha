# Plan: M04 plumbing follow-ups

**Status**: In review
**Zone**: yellow, plus two red lines in `backend/infrastructure`:
acknowledge the empty Cognito custom-domain warning, and remove the
unused API hostname parameters until M03A.

## Goal

Close the gaps found after the plumbing landed. A resumed job must use
the cursor from the moment it takes the lease. The trading calendar
must not keep an empty year, and must refresh the current year. A long
`Retry-After` must not stall a Lambda. `tick` must find stalled jobs
with a query, and one failed start must not drop the others. A secret
cached for one caller must be read again when a later caller needs
another key. The deploy log should not warn about parameters that do
nothing yet.

## Non-goals

- No Alpaca or SEC client.
- No new schedule or HTTP route.
- No API custom domain. M03A adds those parameters when it builds the
  hostname.

## Files

- `backend/lambda/engine/chunked.py`, `store.py`, and their tests
- `backend/lambda/engine/market_calendar.py` and its test
- `backend/lambda/engine/http_client.py` and its test
- `backend/lambda/engine/secrets_read.py` and its test
- `backend/infrastructure/lib/constructs/auth.ts`
- `backend/infrastructure/lib/parameters.ts`
- `docs/plans/reference.md`

## Invariants this change preserves

- Headers and secret values stay out of the log.
- A second caller still does not take a live lease.
- A failed item still keeps the cursor and marks the job `failed`.
- The Cognito custom domain stays conditional. Acknowledging W1030 does
  not create the resource.

## Done when

Engine unit tests pass, the stack test passes, and `cdk synth` no
longer prints W1030 or W2001.

## Rollback

Revert the pull request.

## Open questions

None.
