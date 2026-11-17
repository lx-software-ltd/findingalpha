# Research: data sources

**Status**: Done. Probed on 16 November 2026 (Hong Kong).
**Zone**: green. This memo changes no product code.

The paper key came from the local environment and is not written here.
No account endpoint was called. Figures below are field names, counts,
and public market prints.

## Entry points

The nine URLs in `docs/plans/04-data-ingest.md` were each called once,
plus the extra calls the four questions need (2016 bars, `status=inactive`,
an IEX comparison, a summer timestamp, and one reverse split). Alpaca
documentation checked the same day:
[About Market Data](https://docs.alpaca.markets/us/docs/about-market-data-api),
[Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq),
[Historical bars](https://docs.alpaca.markets/us/reference/stockbars),
[Corporate actions](https://docs.alpaca.markets/us/reference/corporateactions-1).

## Owners

M04. The Alpaca client is M04-T03 (`backend/lambda/engine/alpaca_data.py`).
The SEC client is already `backend/lambda/engine/sec_edgar.py`.

## Callers

No job calls these endpoints yet. M04-T06 and M04-T07 will.

## Existing abstractions

`http_client.get_json` and `secrets_read.read_json_secret`. The secret
id is `findingalpha/alpaca-paper`. The value the owner stores is
`key_id` and `secret_key` (`docs/plans/owner-checklist.md`, O10).

## Answers

1. **Yes.** The free paper key returns `feed=sip` daily bars for past
   dates. AAPL on 2026-11-13 came back with SIP volume 40,187,362 and
   IEX volume 1,220,209 (about 3% of the SIP print), so the SIP request
   is the consolidated tape.    The documented Basic plan still withholds
   SIP for the latest 15 minutes
   ([Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)).
   A request for the current New York day sends `end` as a timestamp 16
   minutes before now. A bare date is read through the present, and the
   free plan refuses it. When the 16:00 close is still inside that
   window, `end` stays on the previous day.
   These calls were for completed sessions, which is what the daily job
   stores. T08 keeps the dollar-volume thresholds. They do not need an
   IEX rescaling.
2. **Yes.** SIP daily bars for AAPL and SPY exist on 2016-01-04
   (`t` = `2016-01-04T05:00:00Z`). The same AAPL request with
   `feed=iex` returned HTTP 200 and an empty `bars` object. The
   backfill uses SIP.
3. **Yes.** `status=inactive` is a real list, and SIP bars exist for
   names that appear only on it. On this day the inactive list had
   19,150 rows, 18,912 of them absent from the active list, and 2,038
   of those on NYSE or NASDAQ. ALXN, CELG, TIF, WORK, and XLNX each
   returned SIP bars with positive volume for 2018–2019. Some delisted
   tickers are on neither list (TWTR, BBBY, SIVB, ATVI on this day), so
   a backtest that starts from Alpaca's lists still misses those
   losers. M06 should say that.
4. **Yes.** Cash dividends include `rate` (cash per share) and
   `ex_date`, plus `payable_date`. Forward and reverse splits include
   `old_rate`, `new_rate`, and `ex_date`.

## Endpoints

### Asset list

`GET https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity`

- Status 200. 14,406 rows, 6,504,127 bytes. No page token. One response
  is the whole list.
- Fields: `id`, `class`, `exchange`, `symbol`, `name`, `status`,
  `tradable`, `marginable`, `maintenance_margin_requirement`,
  `margin_requirement_long`, `margin_requirement_short`, `shortable`,
  `easy_to_borrow`, `borrow_status`, `fractionable`, `attributes`.
- Active counts by exchange: NYSE 2,887, NASDAQ 5,596, AMEX 289,
  ARCA 2,766, BATS 1,674, OTC 1,182, TXSE 12.
- `status=inactive` was 19,150 rows, 8,095,541 bytes, same fields.
  Most inactive rows are OTC.
- Differs from the plan: there is no page size. The list adds
  `borrow_status` and the exchange TXSE. The same symbol can be both
  an active row and an inactive row (SHLD, both ARCA, only the active
  row tradable).

### Trading days

`GET https://paper-api.alpaca.markets/v2/calendar?start=2026-11-01&end=2026-11-14`

- Status 200. 10 sessions, 1,291 bytes. No page token.
- Fields: `date`, `open`, `close`, `session_open`, `session_close`,
  `settlement_date`.
- Sessions in that window: 2026-11-02 through 2026-11-06 and
  2026-11-09 through 2026-11-13.
- This matches the plan's URL. `market_calendar.py` stores the `date`
  values. It does not need the clock fields.

### Daily bars

`GET https://data.alpaca.markets/v2/stocks/bars`

- Status 200 for SIP on 2026-11-13 (AAPL, SPY) and on 2016-01-04
  (AAPL, SPY), and for the inactive names in the answer above.
- Top-level fields: `bars`, `next_page_token`. `bars` is an object
  keyed by symbol. Each bar's fields: `t`, `o`, `h`, `l`, `c`, `v`,
  `n`, `vw`.
- The probes sent `limit` of 1, 2, 3, or 10. A range longer than the
  limit returned `next_page_token`. The plan's `limit=10000` is the
  value the client sends.
- `t` is midnight America/New_York, written in UTC:
  `2024-06-03T04:00:00Z` (EDT) and `2026-11-13T05:00:00Z` (EST). The
  session date is that New York date.
- `end` equal to the session date included that session.
- Differs from the plan: the FAQ's single-symbol example returns
  `bars` as an array plus `symbol`. The multi-symbol URL in the plan
  returns a symbol map. IEX is not a substitute for 2016.

### Dividends and splits

`GET https://data.alpaca.markets/v1/corporate-actions?types=cash_dividend,forward_split,reverse_split`

- Status 200. Top-level fields: `corporate_actions`, `next_page_token`.
- `corporate_actions` is an object. Present groups in these calls:
  `cash_dividends`, `forward_splits`, `reverse_splits`. A group with no
  rows is omitted.
- Cash dividend fields: `id`, `symbol`, `cusip`, `rate`, `special`,
  `foreign`, `ex_date`, `record_date`, `payable_date`, `process_date`.
- Forward split fields: `id`, `symbol`, `cusip`, `old_rate`, `new_rate`,
  `ex_date`, `record_date`, `payable_date`, `process_date`,
  `due_bill_redemption_date`.
- Reverse split fields: `id`, `symbol`, `old_cusip`, `new_cusip`,
  `old_rate`, `new_rate`, `ex_date`, `record_date`, `payable_date`,
  `process_date`. `new_symbol` was absent on the row returned here.
- Page size is the `limit` parameter. The documented default is 100.
  A window with one dividend and one split fit in one page. A request
  with `limit=1` returned `next_page_token`.
- `start` and `end` select `process_date`, not the ex-date. A request
  for 2024-06-10 returned 144 rows. All 144 had `process_date`
  2024-06-10. Six had `ex_date` 2024-06-10. The other ex-dates on that
  page ran back to about a month earlier. The client returns
  `processDate` and `exDate` and does not drop rows. T06 files each
  row under its ex-date.
- Future process dates are returned. On 16 November 2026 the window
  16 November through 30 November returned 968 rows. Tuesday
  16 February 2027, about 90 days ahead, returned 6. For the ex-date
  10 June 2024, one row was processed three days before that ex-date
  and one was processed 51 days after. Of the 968 rows, 967 had a
  process date within 75 days of the ex-date and one was 335 days
  later. T06 asks for seven days before the session through 75 days
  after, then keeps `exDate` equal to the session.
- Differs from the plan: the body is grouped by type, not a flat list.
  Our `cashPerShare` is `rate`. Our split ratio is `old_rate` to
  `new_rate`. Our `payDate` is `payable_date`. `special`, `foreign`,
  and `sub_type` are kept, because a return of capital is not a
  dividend. A reverse split may include `new_symbol`, kept as
  `newSymbol`.

### News

`GET https://data.alpaca.markets/v1beta1/news?symbols=AAPL&start=2024-06-03T00:00:00Z&end=2024-06-04T00:00:00Z&limit=50`

- Status 200. 12 items, 11,069 bytes. `next_page_token` was null for
  this window.
- Top-level fields: `news`, `next_page_token`.
- Item fields: `id` (number), `headline`, `summary`, `author`,
  `content`, `created_at`, `updated_at`, `url`, `symbols`, `source`,
  `images`.
- Differs from the plan: `content` is the article body. The client
  drops `content`, `author`, `images`, and `updated_at`. `createdAt`
  is `created_at`.

### Ticker to CIK

`GET https://www.sec.gov/files/company_tickers_exchange.json`

- Status 200. 10,404 rows, 521,997 bytes. One response.
- Top-level fields: `fields`, `data`. `fields` is `cik`, `name`,
  `ticker`, `exchange`.
- This matches `sec_edgar.ticker_map`.

### Company profile

`GET https://data.sec.gov/submissions/CIK0000320193.json`

- Status 200. 163,926 bytes.
- Top-level fields include `cik`, `sic`, `sicDescription`, `name`,
  `tickers`, `exchanges`, `fiscalYearEnd`, `filings`, and also
  `addresses`, `phone`, and `ein`.
- `filings` has `recent` and `files`. `recent` columns include `form`,
  `filingDate`, `accessionNumber`, `primaryDocument`, `items`,
  `reportDate`.
- Differs from the plan: the payload carries address, phone, and tax
  identifiers. T07 stores `sic` and the filing index, not those fields.
  The field names are recorded here and the values are not.

### Company numbers

`GET https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json`

- Status 200. 3,859,564 bytes.
- Top-level fields: `cik`, `entityName`, `facts`.
- `facts` keys: `dei`, `ffd`, `us-gaap`.
- A tag has `label`, `description`, `units`. A USD fact has `start`,
  `end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, `frame`.
- This matches `fundamentals_pit.py`. `ffd` is an extra taxonomy the
  mapper does not read.

### Filings of a day

`GET https://www.sec.gov/Archives/edgar/daily-index/2024/QTR2/master.20240603.idx`

- Status 200. 466,696 bytes, 5,449 lines.
- A text header, then a line of dashes, then
  `CIK|Company|Form|Date Filed|Filename`.
- This matches `sec_edgar.parse_master`.

## Tests

Re-run the probe with `python3 scripts/probe_data_sources.py`. It reads
`ALPACA_PAPER_KEY_ID`, `ALPACA_PAPER_SECRET_KEY`, and
`SEC_CONTACT_EMAIL` from the environment and prints field names and
counts. M04-T03 tests the client against trimmed fixtures in
`backend/lambda/engine/test_fixtures/`. Those fixtures use invented
names and `example.com`.

## Production signals

The Basic plan documents 200 historical requests a minute and history
since 2016
([About Market Data](https://docs.alpaca.markets/us/docs/about-market-data-api)).
The client stays at or under 150 a minute, which is the cap in
`docs/plans/04-data-ingest.md`. Containers share that cap through the
`RATE#alpaca` / `MINUTE` row. A process also spaces its own calls.
SEC calls stay at or under 5 a second in `sec_edgar.py`.

## History

The milestone plan was written from documentation. This is the first
live pass. `sec_edgar.py` and `fundamentals_pit.py` already follow the
SEC shapes above.

## Open questions

- Delisted names that Alpaca does not list at all (TWTR, BBBY, SIVB,
  ATVI on this day) stay out of the backtest. M06 states that bias.
- A symbol can have an active row and an inactive row. T08 reads the
  active list only.
- T07 must not persist `addresses`, `phone`, or `ein` from the
  submissions document.
- The free plan's 15-minute SIP hold does not affect a job that reads
  yesterday's session. It would matter for a same-session request.
