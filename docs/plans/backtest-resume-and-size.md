# Plan: Resume a backtest, and set its size

**Status**: In review
**Zone**: yellow

## Goal

Tick can resume a backtest whose saved `portfolioSize` came back from DynamoDB as a `Decimal`. A Run now for `backtest`, from the dashboard or a key, can set `portfolioSize` to an integer from 10 to 40. Other jobs stay as they are.

## Non-goals

- Do not deploy, and do not start the live size 15 or 30 runs.
- Do not write `docs/research/backtest-2017-2026.md`.
- Do not change `contracts/`, and do not teach `portfolio_size` to accept a `Decimal` or a float. The resumed event has to carry a JSON integer.
- Do not resume a failed job that has no failure count.

## Files

- `backend/lambda/engine/chunked.py` and `test_chunked.py`
- `backend/lambda/engine/api_handler.py` and `test_public_api.py`
- `apps/admin_web/src/pages/SystemPage.tsx`, `SystemPage.test.tsx`, `ConfirmDialog.tsx`, `useSystemStatus.ts`
- `apps/admin_web/src/lib/mock/fixtures.ts` so the mock System page shows the backtest row
- `docs/plans/reference.md` for the request body

## Invariants this change preserves

- A whole-number `Decimal` is encoded as a JSON integer. A fractional `Decimal` still cannot be encoded.
- An empty body starts `backtest` at the register size, with no `params` on the invoke.
- `portfolioSize` is forwarded only for `backtest`. A body on any other job is refused and does not invoke.
- A size outside 10 to 40, or a value that is not an integer, is 400 and does not invoke.
- Run now for every other job still posts with no body.

## Done when

- `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
- `python3 -m ruff check backend/lambda scripts .cursor/hooks`
- `npm test` in `apps/admin_web`
- The mock System page: open the backtest confirm, refuse 9, send 15, and still send `ingest_daily` with no body.

## Rollback

Revert the commit. A resumed backtest would stall on tick again, and every backtest would use the register size.

## Open questions

None. The owner asked for both fixes.
