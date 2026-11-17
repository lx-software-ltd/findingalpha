# Plan: stop a SIP bar request inside the free window

**Status**: Done
**Zone**: yellow

## Goal

A daily bar request for the current New York day must not ask Alpaca for SIP data inside the last 15 minutes. The free plan answers that query with HTTP 403, so the 16 Nov 2026 session was never stored.

## Non-goals

- Switching the feed to IEX. The consolidated tape stays `sip`.
- Changing corporate actions, news, or which jobs an API key may start.
- Fetching a session whose close is still inside the withheld window.

## Files

- `backend/lambda/engine/alpaca_bars.py`
- `backend/lambda/engine/alpaca_data.py`
- `backend/lambda/engine/test_alpaca_data.py`
- `docs/research/data-sources.md`

## Invariants this change preserves

Historical dates stay `YYYY-MM-DD`. The feed stays `sip`. A request whose end is before the current New York day is unchanged. Nothing is written when the session close is still inside the withheld window.

## Done when

`python3 -m unittest backend.lambda.engine.test_alpaca_data` shows the current New York day ending 16 minutes ago, and a close inside that window ending on the previous day. `python3 -m ruff check backend/lambda/engine/alpaca_bars.py backend/lambda/engine/alpaca_data.py` passes.

## Rollback

Revert the commit. Stored price files stay.

## Open questions

None.
