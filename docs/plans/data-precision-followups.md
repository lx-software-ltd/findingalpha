# Plan: data precision follow-ups

**Status**: Draft. The owner chose these items in chat on 16 November
2026. Nothing is built yet, and each red step still asks before its
write.
**Zone**: red for `contracts/fundamentals.json`,
`contracts/methodology.json`, and any route in
`backend/infrastructure`. Yellow for the engine modules. Green for
the memos.

## Goal

Make market cap, net debt, and the HTTP transport more exact, and add
the data ideas the owner picked. The list came from comparing this
repository with the Python client of FinancialData.Net
(<https://github.com/financialdatanet/fdnpy>) on 16 November 2026.
That client is a thin wrapper over a paid API. We take ideas from its
field list and its transport. We do not take its code or its data.

Fourteen steps in three stages:

1. Correctness and transport, before the first live run (`DP-01` to
   `DP-07`).
2. Methodology proposals for the owner's review in M05 (`DP-08` to
   `DP-11`).
3. Later data for the committee, the brief, and the API (`DP-12` to
   `DP-14`).

## Starts when

The owner asked for this plan to run after the open points are
closed. Those points are not part of this plan. They are listed so the
gate can be checked:

- Pull request 14 is merged (filings stall on a session with no SEC
  index, and the coverage report float write).
- Pull request 15 is merged (universe and SIC sectors).
- M04-T09 is merged and covers the six points from the review of pull
  request 13:
  1. A resumed backfill reuses the saved `start` and `end`. It does
     not work out "yesterday" again.
  2. `tick` can route a job named `ingest_filings_refresh#<date>`,
     and finished rows of that kind do not pile up.
  3. A job calls `refresh_corporate_actions` for a recent window.
  4. The first filings run with no cursor is bounded.
  5. The kill switch is read once per call. Either accept that a run
     in flight finishes its invocation, or read it once per chunk item.
  6. One bar with a price at or below zero fails a whole backfill
     month. Decide what the first run does when that happens.

Stage 1 should land before M04-T11. T11 builds the first universe and
runs both backfills, and `DP-01` to `DP-03` change what those produce.
If T11 has already run, stage 1 still applies. It then costs one more
`backfill_fundamentals` run and one rewrite of the corporate-action
files.

## Non-goals

- No paid data source and no new dependency. The Lambda stays on the
  standard library. `requests` is not added.
- No factor enters the composite without the owner's approval in the
  M05-T01 memo.
- No forecast of future earnings dates. Only dates already filed.
- No insider names. See `DP-13`.
- No change to the Alpaca cap of 150 requests a minute or the SEC cap
  of 5 a second.

## Files

```
backend/lambda/engine/share_count.py        test_share_count.py   (new)
backend/lambda/engine/universe.py           test_universe.py
backend/lambda/engine/snapshot.py           test_snapshot.py      (M05-T03)
backend/lambda/engine/fundamentals_pit.py   test_fundamentals_pit.py
backend/lambda/engine/http_client.py        test_http_client.py
backend/lambda/engine/alpaca_data.py        test_alpaca_data.py
backend/lambda/engine/ingest_prices.py      test_ingest_prices.py
backend/lambda/engine/ingest_fundamentals.py  test_ingest_fundamentals.py
backend/lambda/engine/factors_*.py          (stage 2, after approval)
scripts/probe_data_sources.py
contracts/fundamentals.json                 (red)
contracts/methodology.json                  (red, stage 2)
docs/research/methodology-provisional.md    (M05-T01 memo)
docs/research/data-sources.md
docs/plans/reference.md
```

## Invariants this change preserves

- Nothing uses a number before its `filed` date.
- A missing input gives `None`. Two steps below ask the owner whether
  a missing tag may count as zero. Until the owner answers, it does
  not.
- Raw and adjusted prices stay in separate files.
- Headers and secret values stay out of the log and out of error
  text.
- Thresholds live in the register. No threshold literal in a factor.
- `IngestEnabled` off means no outbound request.
- A second run of a job writes the same files.

## One contract change, one backfill

`ingest_fundamentals.trim_facts` keeps only the mapped tags, so a tag
added later is not in the stored files. Every new tag in this plan
therefore goes into `contracts/fundamentals.json` in **one** red-zone
change, before the fundamentals backfill:

| Field | Kind | Tags, first match per period wins | Used by |
| --- | --- | --- | --- |
| `weightedDilutedShares` | shares over a period | `WeightedAverageNumberOfDilutedSharesOutstanding` | `DP-02` |
| `shortTermInvestments` | stock | `ShortTermInvestments`, `MarketableSecuritiesCurrent`, `AvailableForSaleSecuritiesDebtSecuritiesCurrent` | `DP-08` |
| `shareBasedCompensation` | flow | `ShareBasedCompensation`, `AllocatedShareBasedCompensationExpense` | `DP-09` |

The contract has two sections today, `flows` and `stocks`, both read
as USD except `sharesOutstanding`. `weightedDilutedShares` fits
neither. Give it a third section, for example `shareFlows`, so the
USD flow code never sums it. `trim_facts` and `load_tag_maps` then
read three sections.

Adding a tag changes no formula. The fields sit unused in the
point-in-time rows until the register names them. The coverage report
then shows how many companies report each one, which the owner needs
for the stage 2 decisions. Bump `version` to 2.

## Stage 1: correctness and transport

### DP-01 Split-adjust the share count

Why: `universe.py` multiplies the last filed share count by the raw
close. A split between the count date and the price date makes market
cap wrong by the split ratio until the next filing. After a 10-for-1
split the company looks ten times smaller, and ten times cheaper on
`earningsYield` and `fcfYield`. A reverse split errs the other way.
M05-T03 plans the same multiplication in `snapshot.py`.

- `share_count.split_factor(splits, after, through)`: the product of
  `splitTo / splitFrom` over forward and reverse splits with
  `after < exDate <= through`. No split gives 1.
- `share_count.shares_as_of(rows_as_of, splits, date)` returns the
  adjusted count, the count date, and the source (`DP-02`).
- `through` is the price date. `after` depends on the tag, so the
  point-in-time row for a share count also records its `tag`:
  - `dei:EntityCommonStockSharesOutstanding` is a count on a stated
    date. `after` is the fact's `end`.
  - `CommonStockSharesOutstanding` is a balance-sheet count.
    Statements issued after a split restate it, so `after` is the
    `filed` date.
  This rule is unconfirmed. See the open questions.
- Splits come from one compact file,
  `corporate-actions/splits.jsonl.gz` (`symbol`, `exDate`,
  `splitFrom`, `splitTo`), rewritten by the daily job and the
  backfill. Reading one file per session is too slow for a build.
- `universe.py` and `snapshot.py` both call `shares_as_of`. Neither
  multiplies a filed count by a price directly.

Tests: a forward split inside the window; a reverse split; a split on
the `after` date is not applied; a split after the price date is not
applied; two splits multiply; a symbol with no split is unchanged;
each tag uses its own `after` date.

### DP-02 Fallback share count

Why: the universe drops a company with no `sharesOutstanding`. The
SEC data API only carries facts that apply to the whole filing
entity. A company that reports its count per share class may have no
such fact.

- Read `weightedDilutedShares` in `fundamentals_pit.normalise`. It is
  a period fact in `shares`, not USD. Today only `sharesOutstanding`
  reads share units, so this needs its own branch. Take the row with
  the latest `end`. Never sum it and never build a trailing twelve
  months from it.
- `shares_as_of` uses it only when `sharesOutstanding` is missing or
  older than 450 days (`STOCK_FRESH_DAYS`). `after` is then that
  row's `filed` date, for the same reason as the balance-sheet count.
- It is an average over the period, not a count on a date, so it lags
  a buyback or an issue. That is the price of having a number at all.
- The member row records `sharesSource` (`cover` or
  `weightedDiluted`). The universe row counts the fallbacks.

Tests: cover count present; cover count missing; cover count stale;
both missing gives `None` and the company is dropped as today.

At T11, list the companies that used the fallback in the pull request.

### DP-03 Retry a dropped connection

Why: `http_client.get_text` retries HTTP statuses only. A reset, a
timeout, or a DNS failure raises on the first attempt (checked on
16 November 2026). One reset during a backfill chunk marks the job
`failed`, and `tick` resumes only `running` jobs.

- Treat `urllib.error.URLError`, `TimeoutError`, `ConnectionError`,
  and `http.client.HTTPException` like a 5xx: the same four attempts
  and the same backoff.
- After the last attempt raise `HttpNetworkError` with the exception
  type name. No header and no query string in the message.

Tests: two resets then a body gives three calls; four timeouts raise;
the log holds no header value.

### DP-04 Ask for compressed responses

Why: neither client sends `Accept-Encoding`. The SEC developer FAQ
lists `Accept-Encoding: gzip, deflate` in its sample request headers.
One company-facts file is 3.9 MB uncompressed
(`docs/research/data-sources.md`).

- `http_client` adds `Accept-Encoding: gzip` when the caller did not
  set it, and inflates the body when the response says
  `Content-Encoding: gzip`.
- A response with no such header is read as today.
- Extend `scripts/probe_data_sources.py` to print the bytes received
  with and without compression for one company-facts file and one
  bars page. Record both numbers in the data-sources memo. Alpaca's
  support for it is not confirmed yet.

Tests: a gzip body; a plain body; a body that claims gzip and is not
raises `ValueError`.

### DP-05 Provider error text on the job run

Why: `str(HttpStatusError)` is `HTTP 403`. The job run stores that and
drops the provider's reason.

- `HttpStatusError.__str__` becomes `HTTP <status>: <reason>`. The
  reason is the `message` field of a JSON body, else the body, with
  line breaks removed and cut to 200 characters.
- The request headers are never part of it.

Tests: a JSON body with `message`; an HTML body; a long body is cut.

### DP-06 Keep the security identifier on corporate actions

Why: Alpaca returns `cusip` on dividends and forward splits, and
`old_cusip` and `new_cusip` on reverse splits. `alpaca_data._action`
drops them. The identifier ties a row to a security when a ticker is
reused.

- `_action` adds `cusip`, `oldCusip`, and `newCusip`. A missing value
  is `None`.
- No join uses them yet. They are stored for audit and for the
  reused tickers in `reference/symbol-reuse.json`.
- They are not shown on the dashboard or the public API.

Tests: the dividend and forward-split fixtures carry `cusip`, and a
new reverse-split fixture carries the other two. Use invented values.
The current test asserts `cusip` is absent. Change that assertion in
the same pull request.

### DP-07 Reuse the connection

Why: each request opens a new TLS connection. From the agent machine
a new connection cost 45 ms and a reused one 3 ms. The gain is small
for Alpaca, where the rate limit sets the pace, and larger for the
SEC backfill.

- The default opener keeps one `http.client.HTTPSConnection` per
  host. A caller-supplied `opener` is used as today.
- A reused connection that the server closed is retried once on a
  new connection (`DP-03`).
- Do this last in stage 1. Skip it if the T11 timing shows requests
  already wait on the rate limiter.

Tests: two calls to one host use one connection; a closed connection
is replaced.

## Stage 2: proposals for the M05-T01 memo

These change `contracts/methodology.json`. Add each as a row in
`docs/research/methodology-provisional.md` with the coverage figure
from the report, and wait for the owner (O11). Code follows the M05
rules: tests first, the golden file changes in the same pull request.

### DP-08 Short-term investments in net debt

Three formulas subtract `cash`: `investedCapital` (in `roic`), the
numerator of `netDebtToEbitda` (and so the `debtCeiling` filter), and
`enterpriseValue` (in `earningsYield` and `fcfYield`). The proposal
subtracts `cash + shortTermInvestments` in all three. Today a company
that holds most of its liquidity in securities looks more indebted
and more expensive than it is.

Owner question: many companies have no such tag because they hold
none. The M05 rule is that a missing input gives `None`, never zero.
Does a missing `shortTermInvestments` count as zero here, as an
exception written into the register, or does it make the factor
`None`?

### DP-09 Free cash flow after stock compensation

`freeCashFlow_ttm` after subtracting `shareBasedCompensation_ttm`.

Owner question: replace the current definition in `fcfMargin` and
`fcfYield`, or keep both and add `fcfYieldAfterStockPay`? The same
missing-tag question as `DP-08` applies.

### DP-10 Net share issuance

`netShareIssuance12m = shares[t] / shares[t - 4 quarters] - 1`, both
counts split-adjusted with `DP-01`. Direction `lower`. Group
`quality`. It needs no new data.

### DP-11 Beta against the benchmark

`beta252 = covariance(stock, SPY) / variance(SPY)` on daily log
returns of adjusted closes over 252 sessions. Like `volatility252`
it is defined in the register and is not part of the composite. It
goes on the committee fact sheet (M08-T05) and is available to
portfolio construction (M09-T04).

Owner question: is a three-year figure (756 sessions) wanted as
well?

## Stage 3: later data

### DP-12 Earnings dates from 8-K filings

Lands with M08-T05 and M10-T02.

- The daily index has no item codes. The SEC submissions document
  has an `items` column for recent filings
  (`docs/research/data-sources.md`). For each 8-K row we keep, read
  `items` for that accession and store it on the filing row.
- Item 2.02 marks a results release. The fact sheet's `E` facts and
  the daily watch list then say "8-K, results" in place of "8-K".
- Keep `items` only. Do not store the address, phone, or tax number
  fields of the submissions document.
- Limit the lookups to holdings and the shortlist unless the request
  count is small for the whole universe. Measure first.

### DP-13 Insider trades and short interest

Lands with M08-T05, as fact-sheet context. Not a factor.

1. Spike memo first, as in M04-T01: the free source for each, its
   terms of use, the format, and the request count. Form 4 is on
   EDGAR. The short-interest source is not confirmed.
2. Form 4: keep rows of form `4` for universe issuers from the daily
   index, then read the ownership XML for the transaction code, the
   shares, and the price.
3. Do not store the insider's name or CIK. Store the relationship
   flags (officer, director, ten percent owner) and the amounts.
4. Fact sheet: open-market buys and sells in the last 90 days, and
   the latest short interest with days to cover.

### DP-14 Field selection and filters on the screen route

Lands with M06-T06. The route itself is red there.

- `GET /v1/admin/screens/latest?fields=symbol,composite,roic` returns only
  those keys.
- Filters use `field[op]=value` with `eq`, `in`, `gt`, `gte`, `lt`,
  `lte`. An unknown field or operator is a 400.
- `format=csv` returns the same rows as CSV.
- The partner mirror under `/v1/partner` gets the same behaviour through
  the `research` scope.

## Done when

- Engine unit tests pass, including every test named above.
- `python3 -m ruff check backend/lambda scripts .cursor/hooks` is
  clean, and `python3 scripts/check-contracts.py` passes after the
  contract change.
- A fixture company with a 10-for-1 split between its count date and
  the price date keeps the same market cap before and after the
  split.
- The data-sources memo records the compressed and uncompressed byte
  counts.
- The M05-T01 memo holds the four stage 2 rows and the owner's
  answer to each.
- At T11 the pull request lists the companies on the fallback share
  count and five real splits checked by hand against `DP-01`.

## Rollback

Each step is its own pull request and reverts alone. Reverting the
contract change leaves unused fields in stored files, which is
harmless. Reverting `DP-01` restores the unadjusted market cap, so
rebuild the universe after it.

## Open questions

- `DP-01` and `DP-02`: which date a split is counted from. The plan
  assumes a cover-page count is the count on its stated date, and
  that a balance-sheet count or a weighted average is already
  restated for a split made before the filing. Check five real
  splits at T11 and write the answer in the data-sources memo before
  trusting either rule.
- `DP-08` and `DP-09`: whether a missing tag counts as zero. For the
  owner.
- `DP-11`: one-year beta only, or three-year as well. For the owner.
- `DP-13`: which free short-interest source, and its terms.
- `DP-06`: the identifier is licensed data. It stays in the private
  bucket unless the owner decides otherwise.
