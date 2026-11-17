# Plan: stop a SIP bar request inside the free window

**Status**: Done
**Zone**: yellow

## Goal

A daily bar request must not ask Alpaca for SIP data inside the last 15 minutes. Alpaca reads a bare date through the end of that New York day, so the first 16 minutes after midnight are inside the window too. The free plan answers that query with HTTP 403, so the 16 Nov 2026 session was never stored. A run whose close is still inside the window waits and writes nothing.

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

Historical dates stay `YYYY-MM-DD` once the end of that New York day is outside the window. The feed stays `sip`. Nothing is written when the session close is still inside the withheld window, and that run is `not_ready`.

## Done when

`python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'` shows the current New York day ending 16 minutes ago, the first 16 minutes after midnight still using a timestamp, the 16:16 boundary, and a daily run inside the window returning `not_ready`. `python3 -m ruff check backend/lambda scripts .cursor/hooks` passes.

## Rollback

Revert the commit. Stored price files stay.

## Open questions

None.
