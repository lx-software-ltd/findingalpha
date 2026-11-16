# Plan: M04 data ingest

**Status**: T02, T04, and T05 are on main. T01's memo is `docs/research/data-sources.md` (all four answers are yes, so bars use `feed=sip`). T03 is next. The live coverage report stays in T07.
**Zone**: yellow. Red parts: new schedules and routes in CDK, and the
first version of `contracts/methodology.json` (universe section).

## Goal

Every US trading day, store what the screen and the ledger need:
prices, dividends and splits, company fundamentals as they were known
on each date, new filings, and news for the names we hold or shortlist.
Build the list of stocks the screen may consider (the universe). All
from free sources.

## Non-goals

- No factor calculation (M05). No scoring (M06).
- No intraday data, options, or non-US markets.
- No X/Twitter, no paid transcripts (deferred by the owner).
- No filing text extraction. Only the filing index and XBRL numbers.
- No pandas, numpy or pyarrow in the Lambda. Standard library only, so
  the same code runs in the Lambda and in the backtest.

## Files

```
backend/lambda/engine/http_client.py      test_http_client.py
backend/lambda/engine/secrets_read.py     test_secrets_read.py
backend/lambda/engine/s3io.py             test_s3io.py
backend/lambda/engine/chunked.py          test_chunked.py
backend/lambda/engine/market_calendar.py  test_market_calendar.py
backend/lambda/engine/alpaca_data.py      test_alpaca_data.py
backend/lambda/engine/sec_edgar.py        test_sec_edgar.py
backend/lambda/engine/fundamentals_pit.py test_fundamentals_pit.py
backend/lambda/engine/ingest_prices.py    test_ingest_prices.py
backend/lambda/engine/ingest_fundamentals.py  test_ingest_fundamentals.py
backend/lambda/engine/ingest_news.py      test_ingest_news.py
backend/lambda/engine/universe.py         test_universe.py
backend/lambda/engine/jobs_handler.py     (register jobs)
backend/lambda/engine/api_handler.py      (two routes)
backend/lambda/engine/test_fixtures/      (small recorded payloads)
contracts/methodology.json   (version + universe section only)
contracts/fundamentals.json  contracts/sic-sectors.json
backend/infrastructure/lib/schedules.ts  api-routes.ts   (red)
apps/admin_web/src/components/system/DataStatus.tsx  (+ mock, test)
docs/research/data-sources.md
```

## Invariants this change preserves

- Fundamentals are stored with the date they were filed. Nothing later
  may use a number before its `filed` date.
- Raw (unadjusted) prices are never overwritten by adjusted ones. They
  are separate files.
- Each daily write is keyed by date, so running a job twice gives the
  same files.
- Rate limits: Alpaca at most 150 requests a minute, SEC at most 5 a
  second, with the contact email in the `User-Agent`.
- `IngestEnabled` off means no outbound request at all.
- Secrets are read at call time from Secrets Manager and never logged.

## External endpoints

Confirm each against the provider's current documentation in T01. The
plan was written from documentation, not from live calls.

| Purpose | Request |
| --- | --- |
| Asset list | `GET https://paper-api.alpaca.markets/v2/assets?status=active&asset_class=us_equity` |
| Trading days | `GET https://paper-api.alpaca.markets/v2/calendar?start=<date>&end=<date>` |
| Daily bars | `GET https://data.alpaca.markets/v2/stocks/bars?symbols=<list>&timeframe=1Day&start=<date>&end=<date>&adjustment=<raw or all>&feed=sip&limit=10000&page_token=<token>` |
| Dividends and splits | `GET https://data.alpaca.markets/v1/corporate-actions?types=cash_dividend,forward_split,reverse_split&start=<date>&end=<date>` |
| News | `GET https://data.alpaca.markets/v1beta1/news?symbols=<list>&start=<iso>&end=<iso>&limit=50` |
| Ticker to CIK | `GET https://www.sec.gov/files/company_tickers_exchange.json` |
| Company profile | `GET https://data.sec.gov/submissions/CIK<10 digits>.json` (SIC code, recent filings) |
| Company numbers | `GET https://data.sec.gov/api/xbrl/companyfacts/CIK<10 digits>.json` |
| Filings of a day | `GET https://www.sec.gov/Archives/edgar/daily-index/<year>/QTR<n>/master.<yyyymmdd>.idx` |

Alpaca headers: `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`. SEC header:
`User-Agent: findingalpha <SEC_CONTACT_EMAIL>`.

## Steps

### M04-T01 Spike and memo (no product code)

With the owner's paper keys in a local environment file that is not
committed, make one request to each endpoint above. Write
`docs/research/data-sources.md` from the research template with, for
each: the status, the response shape actually seen (field names only,
no account data), page size, and anything that differs from this plan.

Answer these in the memo. Each is a stop-and-ask point if the answer is
no:

1. Does the free plan return `feed=sip` daily bars for past dates? If
   not, the fallback is `feed=iex`, whose volume is a small share of
   the real volume, and the liquidity thresholds in T08 must be
   rescaled. Ask the owner.
2. Do daily bars go back to 2016?
3. Are bars available for symbols that are no longer listed (asset
   list with `status=inactive`)? This decides how biased the backtest
   is (M06).
4. Does the corporate-actions endpoint give the per-share cash amount
   and the ex-date?

### M04-T02 Plumbing

Tests first for each.

- `http_client.py`: `get_json(url, headers, timeout)` and
  `get_text(...)` on `urllib.request`. Retries on 429 and 5xx with
  exponential backoff, honours `Retry-After`, at most 4 attempts.
  Closes HTTP error bodies (see `_read_http_error` in the sibling
  `http_common.py`). A `RateLimiter(per_second)` class that sleeps.
  Never logs headers.
- `secrets_read.py`: `read_json_secret(secret_id, required_keys)`
  returns a dict or raises `NotConfigured`. Cache per container for 5
  minutes. Modelled on the sibling `secret_store.py`.
- `s3io.py`: `put_jsonl_gz(bucket, key, rows)`,
  `get_jsonl_gz(bucket, key)` (generator), `put_json`, `get_json`,
  `exists`, `list_keys(prefix)`.
- `market_calendar.py`: `sessions(start, end)` and
  `previous_session(today_new_york)`. Cache the calendar for the year
  in `reference/calendar/year=<yyyy>.json`.
- `chunked.py`: long jobs that do not fit in 15 minutes.
  - State row `JOB#<job>` / `STATE`: `status` (`idle`, `running`,
    `done`, `failed`), `cursor`, `total`, `leaseUntil`, `updatedAt`.
  - `run(job, items, process, context)`: take the lease with a
    conditional update (`leaseUntil` missing or in the past), process
    items from the cursor, save the cursor after each item, stop when
    `context.get_remaining_time_in_millis()` is under 120,000, release
    the lease. Mark `done` when the cursor reaches the end.
  - The `tick` job (every 15 minutes) looks at every `STATE` row with
    status `running` and no live lease and invokes that job again.
  - Tests: resume from a cursor; a second caller does not get the
    lease; a failing item marks the job `failed` and keeps the cursor.

### M04-T03 Alpaca data client

`alpaca_data.py`: `list_assets()`, `daily_bars(symbols, start, end,
adjustment)` (generator that follows `next_page_token`; batches of 200
symbols per request), `corporate_actions(start, end)`,
`news(symbols, start, end)`. Each returns plain dicts with our own
field names:

- Bar: `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`,
  `vwap`.
- Action: `symbol`, `type`, `exDate`, `payDate`, `cashPerShare`,
  `splitFrom`, `splitTo`.
- News: `id`, `symbols`, `headline`, `summary`, `source`, `url`,
  `createdAt`. Do not store article bodies.

Tests use trimmed recorded responses in `test_fixtures/`.

### M04-T04 SEC client

`sec_edgar.py`: `ticker_map()`, `submissions(cik)`,
`company_facts(cik)`, `daily_index(date)`. `daily_index` parses the
pipe-separated `master` file (skip the header lines down to the row of
dashes) into rows of `cik`, `company`, `form`, `filed`, `path`. A 404
for a date means the index is not published yet or it was not a
business day: return an empty list, do not fail.

### M04-T05 Point-in-time fundamentals

`contracts/fundamentals.json` maps our field names to XBRL tags. For
each period, the first tag that has a value wins, and a later tag
fills periods the earlier tags do not cover:

```json
{
  "version": 1,
  "flows": {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "costOfRevenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "grossProfit": ["GrossProfit"],
    "operatingIncome": ["OperatingIncomeLoss"],
    "netIncome": ["NetIncomeLoss"],
    "incomeTax": ["IncomeTaxExpenseBenefit"],
    "pretaxIncome": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
    "interestExpense": ["InterestExpense", "InterestExpenseDebt"],
    "depreciationAmortization": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
    "operatingCashFlow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"]
  },
  "stocks": {
    "totalAssets": ["Assets"],
    "currentAssets": ["AssetsCurrent"],
    "currentLiabilities": ["LiabilitiesCurrent"],
    "totalLiabilities": ["Liabilities"],
    "equity": ["StockholdersEquity"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "longTermDebt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "shortTermDebt": ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"],
    "sharesOutstanding": ["dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]
  }
}
```

The tag list is a starting point. T05 ends with a coverage report
(below) that shows which fields are missing most often. Extend the
lists from that report.

`fundamentals_pit.py`:

1. `normalise(company_facts)` produces rows: `field`, `kind` (`flow` or
   `stock`), `start`, `end`, `value`, `filed`, `form`, `fy`, `fp`.
   Keep only USD units (shares for share counts) and only forms 10-K,
   10-Q and their amendments.
2. Classify each flow row by its length in days: 80 to 100 quarter, 170
   to 190 half, 260 to 285 nine months, 350 to 380 year. Drop others.
3. `as_of(rows, date)` keeps rows with `filed <= date`. When several
   rows describe the same field and period, keep the one filed last.
4. `ttm(rows_as_of, field)`: trailing twelve months. Take the latest
   annual value `FY`. Take the latest year-to-date value `YTD` that
   ends after that fiscal year end, and the year-to-date value for the
   same period one year earlier, `YTD_prev`. Then
   `TTM = FY + YTD - YTD_prev`. A year-to-date value starts when the
   new fiscal year starts, so a quarter that starts mid-year is not
   one, even when it ends on the same day as the longer row. If there
   is no later year-to-date value, `TTM = FY`. If a needed piece is
   missing, return `None`. Never guess.
5. `latest_stock(rows_as_of, field)`: the stock row with the latest
   `end`.
6. `average_stock(rows_as_of, field)`: mean of the latest value and
   the value four quarters earlier. `None` if either is missing.

Tests, with hand-made fixtures for an invented company:

- A number filed on day D is invisible on D-1 and visible on D.
- A restated value replaces the original only from the restatement's
  filing date.
- `ttm` after a 10-K, after a first-quarter 10-Q, and after a
  third-quarter 10-Q, checked against hand arithmetic written in the
  test.
- A company whose fiscal year ends in September.
- A missing prior-year value gives `None`.

### M04-T06 Price ingest

`ingest_prices.py`:

- `ingest_raw_day(date)`: bars with `adjustment=raw` for every active
  NYSE and NASDAQ asset, one file
  `prices/raw/date=<date>/bars.jsonl.gz`. Corporate actions of the day
  to `corporate-actions/date=<date>/actions.jsonl.gz`.
- Quality checks before writing: SPY is present; no bar with a price
  at or below zero; the number of bars is within 15% of the previous
  session's. On failure raise `DataQualityError` with the failing
  check. The job run is `failed` and nothing is written.
- `refresh_adjusted(symbols)`: full history for the universe plus
  `SPY` and `BIL`, written in parts of 100 symbols, twice: once with
  `adjustment=all` (splits and dividends, a total-return series) under
  `prices/adj/` and once with `adjustment=split` (splits only, a price
  series) under `prices/split/`. The difference between the two is the
  dividend return, which M06 and M09 need for the withholding-tax
  calculation. Chunked.
- `backfill_raw(start, end)`: one month per chunk. Chunked.

### M04-T07 Fundamentals, filings, news ingest

- `ingest_fundamentals.refresh(ciks)`: fetch company facts, trim to the
  mapped tags, write the raw file and the point-in-time rows. Chunked.
- `ingest_fundamentals.daily()`: read the newest daily index not yet
  processed (cursor in the job state; usually the day before, because
  the SEC publishes the index late in the US evening). Keep 10-K, 10-Q
  and 8-K rows for universe CIKs. Write the filings file. Call
  `refresh` for CIKs with a 10-K or 10-Q.
- `ingest_fundamentals.coverage_report()`: for the universe, the share
  of companies with a non-`None` TTM for each flow field and a value
  for each stock field. Stored on the universe row. Shown on the
  System page.
- `ingest_news.daily(symbols)`: last three days of news for the
  symbols given (holdings and shortlist; empty until M06 and M09
  exist). Deduplicate by `id`.

### M04-T08 Universe

Thresholds go in `contracts/methodology.json`. This milestone creates
the file with only this section. All values are **provisional** until
the owner confirms them (O11):

```json
{
  "version": 1,
  "universe": {
    "status": "provisional",
    "exchanges": ["NYSE", "NASDAQ"],
    "requireMarginable": true,
    "requireAnnualReportForm": "10-K",
    "excludeSicRanges": [[6000, 6799]],
    "minPriceUsd": 5,
    "minMedianDollarVolumeUsd": 20000000,
    "dollarVolumeWindowSessions": 60,
    "minMarketCapUsd": 2000000000,
    "minFundamentalsYears": 3
  }
}
```

Why each rule exists (write this in the memo for the owner):
marginable is needed for leverage; the 10-K rule drops foreign filers
whose data has different tags; SIC 6000 to 6799 are banks, insurers,
funds and property trusts, where the quality formulas do not mean the
same thing; price, volume and size keep trading costs small.

`universe.build(date)`:

1. Assets: active, tradable, exchange in the list, marginable.
2. Join to the SEC ticker map. Drop symbols without a CIK.
3. From the last 60 raw daily files: last close and median of
   `close * volume`. Apply price and dollar-volume rules.
4. For survivors, make sure fundamentals exist (call `refresh` for
   missing CIKs) and read the SIC code from `submissions`.
5. Apply the SIC exclusion, the 10-K rule, the history rule.
6. Market cap = latest `sharesOutstanding` as of the date times last
   close. Apply the size rule.
7. Sector from `contracts/sic-sectors.json`: a list of
   `{ "from": 1300, "to": 1399, "sector": "Energy" }` ranges covering
   every SIC code, mapped to eleven sectors (Energy, Materials,
   Industrials, Consumer Discretionary, Consumer Staples, Health Care,
   Financials, Technology, Communication, Utilities, Real Estate).
   Build the table from the SEC's SIC code list. A code that matches
   no range maps to `Other` and is counted in the report. The owner
   reviews the table once.
8. Write `universe/date=<date>/members.jsonl.gz` (`symbol`, `cik`,
   `name`, `sic`, `sector`, `close`, `medianDollarVolume`,
   `marketCap`) and the `UNIVERSE#<date>` row with counts at each
   step.

Tests: each rule removes exactly the rows it should from a fixture of
about twenty invented companies; an unmapped SIC lands in `Other`; a
company with fundamentals filed after the date is treated as having
none.

Expected size is 1,000 to 1,500. If the first real build is outside
800 to 2,000, stop and ask.

### M04-T09 Jobs, schedules, routes

Jobs in `jobs_handler.py` (and `contracts/jobs.json`):

| Job | Does | Manual run |
| --- | --- | --- |
| `ingest_daily` | If yesterday in New York was a session: raw day, corporate actions, filings and fundamentals, news. Else `skipped_no_session` | yes |
| `weekly_refresh` | Assets, ticker map, universe build, adjusted refresh | yes |
| `backfill_prices` | Raw bars from 2016-01-01 to yesterday | yes |
| `backfill_fundamentals` | Company facts for every candidate CIK | yes |

Every job checks `kill_switch.is_enabled("ingestEnabled")` first.

CDK (red, ask first): schedules `findingalpha-ingest-daily` and
`findingalpha-weekly-refresh` from `reference.md` section 9, with
`retryAttempts: 0`. Routes `POST /jobs/{jobName}/run` and
`GET /universe/latest`.

`POST /jobs/{jobName}/run`: the job must be in the manual allow-list of
`contracts/jobs.json`, else 404. Invoke `EngineFn` with
`InvocationType="Event"` and
`{"job": name, "trigger": "manual", "by": "<sub>"}`. Return 202
`{"accepted": true}`. Write an audit row. The page then polls
`GET /jobs/runs`.

### M04-T10 Dashboard: data status

On the System page add a **Data** section: universe date and size with
the count after each rule, last raw price date, fundamentals coverage
table, backfill progress (cursor out of total), and a "Run now" button
for each allowed job behind a confirm dialog.

### M04-T11 First run

Needs O10 (paper keys in the secret) and the parameter
`IngestEnabled=true` plus the runtime switch on.

1. Run `backfill_prices` from the dashboard. Watch progress.
2. Run `weekly_refresh`. It triggers the fundamentals backfill for
   candidates.
3. Check: universe size in range; the coverage report shows at least
   90% for revenue, operating income, net income, total assets, equity,
   operating cash flow. Extend `contracts/fundamentals.json` and rerun
   until it does, or stop and ask.
4. Let `ingest_daily` run for five sessions. All five succeed.

## Done when

- Engine unit tests pass, including every test listed above.
- `docs/research/data-sources.md` answers the four questions in T01.
- The dashboard shows a universe between 800 and 2,000 names, raw
  prices from 2016, and coverage of at least 90% on the six fields.
- Five consecutive `ingest_daily` runs succeeded.
- S3 data bucket size is reported in the pull request (expected under
  2 GB).

## Rollback

Set `IngestEnabled=false` in the parameter file and redeploy, or turn
the runtime switch off on the System page. Revert the pull request.
Stored files are harmless and stay.

## Open questions

- The four spike questions in T01.
- Whether financial companies should be in the universe with their own
  formulas later. Out of scope now.
