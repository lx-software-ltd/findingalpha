# Plan: M09 portfolio, ledger, paper broker

**Status**: Draft
**Zone**: red (register sections, `broker*.py`, `orders.py`,
`leverage.py`, `limits.py`, CDK)

## Goal

Turn theses into a target portfolio with deterministic rules, decide
the leverage level, produce order proposals, talk to the Alpaca
**paper** account through an adapter, and keep the system's own ledger
with dividends, withholding tax, margin interest and running costs.
After this milestone the system can say exactly what it would trade
and can prove its books match the broker. It does not yet trade on its
own (M10).

## Non-goals

- No automatic order submission. The only order sent in this milestone
  is a one-share smoke test started by hand.
- No live broker. No code path for a live host.
- No options, no short selling, no withdrawals, no transfers. These
  are not "disabled". They are not written.
- No tax advice. The ledger makes provisions from rates in the
  register. The owner confirms the rates with an adviser (O15).
- No Hong Kong dollar reporting.

## Files

```
docs/research/alpaca-paper.md   docs/research/leverage-overlay.md
contracts/methodology.json      (portfolio, leverage, exits, execution, tax; red)
backend/lambda/engine/limits.py           test_limits.py          (red)
backend/lambda/engine/leverage.py         test_leverage.py        (red)
backend/lambda/engine/portfolio.py        test_portfolio.py
backend/lambda/engine/orders.py           test_orders.py          (red)
backend/lambda/engine/broker.py           test_broker.py          (red)
backend/lambda/engine/broker_alpaca.py    test_broker_alpaca.py   (red)
backend/lambda/engine/ledger.py           test_ledger.py
backend/lambda/engine/tax.py              test_tax.py
backend/lambda/engine/benchmark.py        test_benchmark.py
backend/lambda/engine/reconcile.py        test_reconcile.py
backend/lambda/engine/jobs_handler.py  api_handler.py
backend/infrastructure/lib/schedules.ts  api-routes.ts            (red)
apps/admin_web/src/pages/PortfolioPage.tsx   (+ nav, mock, test)
```

## Invariants this change preserves

- `limits.HARD_LEVERAGE_CAP = 1.5` is a constant in code. The register
  loader rejects a larger `hardCap`. No batch containing a buy can
  leave if it would put gross exposure above the cap.
- With `LeverageEnabled` off the target level is 1.0.
- A sell never exceeds the quantity held. No order has a negative
  resulting position.
- The broker adapter's base URL is the paper host. It raises if
  `BROKER_MODE` is not `paper`.
- Every order has a thesis id and the register hash.
- Order submission is idempotent: our order id is the broker's
  `client_order_id`.
- All sizing arithmetic is in `portfolio.py`, `leverage.py`,
  `orders.py`. No model output is used except `decision`, `conviction`
  and validated kill criteria.
- The capital amount is never in git. The ledger starts from what the
  broker reports.

## Register additions

All provisional until cited or accepted (M07 process).

```json
"portfolio": {
  "status": "provisional",
  "minPositions": 12,
  "maxPositions": 20,
  "minConvictionToBuy": 3,
  "convictionMultipliers": { "3": 0.75, "4": 1.0, "5": 1.25 },
  "maxPositionWeightAtBuy": 0.08,
  "maxPositionWeightHard": 0.10,
  "maxSectorWeight": 0.25,
  "cashBufferWeight": 0.02,
  "minTradeWeight": 0.01,
  "maxMonthlyTurnover": 0.25
},
"leverage": {
  "status": "provisional",
  "hardCap": 1.5,
  "levels": [1.0, 1.25, 1.5],
  "stepUp": {
    "benchmark": "SPY",
    "requireCloseAboveSma": 200,
    "requireSmaFastAboveSlow": [50, 200],
    "maxBenchmarkVolatility20": 0.15,
    "maxPortfolioDrawdown": 0.05
  },
  "stepDown": {
    "toOneAtPortfolioDrawdown": 0.10,
    "toOneWhenBenchmarkBelowSma": 200,
    "toOneAtBenchmarkVolatility20": 0.25
  },
  "trimWhenAboveLevelBy": 0.05,
  "haltBuysAtPortfolioDrawdown": 0.20,
  "marginRateAnnual": 0.065
},
"exits": {
  "status": "provisional",
  "reviewAtLossFromCost": 0.25
},
"execution": {
  "status": "provisional",
  "orderType": "market",
  "timeInForce": "day",
  "wholeSharesOnly": true,
  "maxOrderWeight": 0.12,
  "maxOrdersPerDay": 40
},
"tax": {
  "status": "provisional",
  "dividendWithholdingRate": 0.30,
  "estate": { "exemptionUsd": 60000, "brackets": [] }
}
```

All weights are fractions of the account's own money (equity).
`estate.brackets` is filled in T08 from the current IRS instructions,
not from memory.

## Steps

### M09-T01 Spike and memo

Write `docs/research/alpaca-paper.md` from the Alpaca documentation
and one read-only call to `GET /v2/account` and `GET /v2/clock` with
the paper keys:

1. The request and response fields for: account, positions, submit
   order, get order by client order id, list orders, account
   activities, account configurations.
2. Whether the cash from a sale can pay for a buy on the same day at
   each margin multiplier. M10 sends buys only after the sells of the
   batch have filled, so the answer changes timing, not safety.
3. What the paper account simulates: dividends, margin interest, fees.
   The plan assumes it simulates none of them. T07 depends on the
   answer.
4. Account configuration options (`no_shorting`, the margin
   multiplier). The plan sets `no_shorting` to true.
5. How a duplicate `client_order_id` is answered.
6. The current margin rate, for the register.

### M09-T02 Limits (write this first)

`limits.py` holds the checks that nothing else may weaken.

```python
HARD_LEVERAGE_CAP = 1.5
```

`check_batch(account, positions, orders, prices, register,
target_level)` returns a list of violations. An empty list means the
batch may go. Checks, applied to the portfolio **as it would be after
all orders fill** at the given prices:

1. Gross exposure (sum of position values over equity) is at most
   `min(target_level, register hardCap, HARD_LEVERAGE_CAP)` plus a
   0.5% tolerance for rounding.
2. No position value over equity exceeds `maxPositionWeightHard`.
3. No sector exceeds `maxSectorWeight` (times the target level).
4. No resulting quantity is negative.
5. Every symbol is in the current universe or is being sold.
6. No single order exceeds `maxOrderWeight` of equity.
7. The number of orders is at most `maxOrdersPerDay`.
8. Every order has a thesis id.
9. Buys are absent when buys are halted (T03).

Checks 1 to 3 apply only to a batch that contains a buy. A batch of
sells alone can only lower exposure, and must never be blocked for
being "still too high": that would stop the very sale that reduces
risk.

Falling prices can push exposure above the level without any order
(positions worth 150 on equity of 100 become 120 on 70, which is 1.71
times). `limits.py` cannot prevent that. The daily check in M10 sells
down when exposure is above the level by more than
`trimWhenAboveLevelBy`.

Tests: one per check, a batch that passes, a sells-only batch that
passes while exposure is above the cap, and a property-style test that
tries 1,000 random batches (fixed seed) and asserts that any clean
batch containing a buy leaves gross exposure at or below 1.5.

### M09-T03 Leverage rule

`leverage.py`, pure functions:

- `market_state(spy_adjusted_closes)`: last close, 50-day and 200-day
  averages, 20-session annualised volatility of daily log returns.
- `drawdown(snapshots)`: fall of equity from its highest value.
- `step_down_required(market, drawdown, register)`: true if any
  step-down condition holds.
- `step_up_allowed(market, drawdown, register)`: true only if all
  step-up conditions hold.
- `target_level(current, market, drawdown, register, enabled,
  is_rebalance)`:
  1. Not enabled: 1.0.
  2. Step-down required: 1.0. This applies every day.
  3. On a monthly rebalance, when step-up is allowed and `current` is
     below the highest level: the next level up. One notch per month.
  4. Otherwise: `current`.
  5. The result is clamped to `HARD_LEVERAGE_CAP`.
- `buys_halted(drawdown, register)`: true at or beyond the halt
  drawdown. M11 turns this into a breaker that only the owner resets.

Tests: every branch; never above 1.5 for any input; two notches never
happen in one call; a missing input (short price history) gives 1.0.

Then replay the rule on the M06 backtest equity curve (script-style
job `leverage_overlay`, manual): the level each month, the return with
and without leverage after interest at `marginRateAnnual`, the worst
drawdown of each. Write `docs/research/leverage-overlay.md`. Include
the arithmetic that at 1.5 times, with a 30% maintenance requirement,
a margin call needs a fall of about 52% in the positions. If leverage
did not improve the return per unit of drawdown, say so plainly and
ask the owner whether to keep it.

### M09-T04 Portfolio construction

`portfolio.build_target(theses, screen_rows, sectors, level,
register)` returns `{symbol: weight}`. Deterministic steps:

1. Candidates: active theses with decision `buy` or `hold` and
   conviction at or above `minConvictionToBuy`. Sort by conviction
   (high first), then composite (high first), then symbol.
2. Take candidates in order, skipping one whose sector would then hold
   more than `maxSectorWeight / maxPositionWeightAtBuy` names, until
   `maxPositions`.
3. Raw weight = the conviction multiplier. Scale so the weights sum to
   the exposure target `level - cashBufferWeight`.
4. Cap each at `maxPositionWeightAtBuy`. Give the excess to uncapped
   names in proportion. Repeat until nothing changes. If every name is
   capped, the remainder stays in cash.
5. If a sector's sum exceeds `maxSectorWeight * level`, scale that
   sector's names down. The excess stays in cash.
6. Fewer than `minPositions` names is allowed. The result is simply
   less invested. Record a warning on the target.

A consequence to state in the document and test: leverage is only
reachable with enough names. Twelve names at the 8% cap give at most
96% exposure whatever the level says.

`portfolio.diff(target, positions, equity, prices, register)` returns
trade intents:

1. A held symbol without an active thesis, or with thesis status
   `exit`: sell everything.
2. Others: target value = weight times equity. Quantity =
   `floor(target value / price)`. Trade only when the weight change is
   at least `minTradeWeight`.
3. Turnover cap: if the buys (excluding those funded by exits) exceed
   `maxMonthlyTurnover` of equity, scale all buys down by one factor.
4. Sells are ordered before buys.

Tests with hand-worked examples: caps and redistribution; the sector
cap; the turnover cap; whole shares; an exit; fewer than twelve names;
level 1.5 with twenty names; identical input gives identical output.

### M09-T05 Orders

`orders.py`:

- `propose(intents, thesis_ids, register_hash, reason)` writes
  `ORDER#<orderId>` rows with status `proposed`. `orderId` is a UUID.
  Fields: symbol, side, quantity, reference price, thesis id, register
  hash, reason (`rebalance`, `thesis_exit`, `leverage_step_down`,
  `risk_trim`), batch id.
- `transition(order_id, from_status, to_status, **fields)` with a
  conditional update, so two workers cannot both move an order. Legal
  moves: `proposed -> held -> submitted -> filled | partially_filled |
  canceled | rejected | expired`, and `proposed | held -> vetoed |
  blocked`.
- `submit_batch(batch_id, broker)`: reload account, positions and
  prices; run `limits.check_batch` on the whole batch; on any
  violation mark every order `blocked` with the reasons and return.
  Otherwise submit sells, then buys, each with
  `client_order_id = orderId`. Requires
  `kill_switch.is_enabled("tradingEnabled")`.

Tests: illegal transitions fail; a blocked batch submits nothing; the
switch off submits nothing; a second `submit_batch` on the same batch
submits nothing new.

### M09-T06 Broker adapter

`broker.py`: the interface the rest of the code uses. Methods:
`account()`, `positions()`, `clock()`, `submit_order(order)`,
`order_by_client_id(order_id)`, `orders_since(iso)`,
`activities_since(iso)`, `configure()`. Plus `FakeBroker`, an
in-memory implementation used by every other test in the repository.

`broker_alpaca.py`:

```python
PAPER_HOST = "https://paper-api.alpaca.markets"

def _host() -> str:
    if config.broker_mode() != "paper":
        raise BrokerError("only paper mode exists")
    return PAPER_HOST
```

- Uses `http_client` and `secrets_read` (secret
  `findingalpha/alpaca-paper`).
- `submit_order` sends only: symbol, whole quantity, side, type
  `market`, time in force `day`, `client_order_id`. It refuses a
  symbol whose asset class is not US equity.
- A duplicate client order id is answered by fetching the existing
  order.
- `configure()` sets `no_shorting` to true and, when `LeverageEnabled`
  is off, the lowest margin multiplier the API offers, so the broker
  itself refuses borrowing.
- There is no function for transfers, withdrawals, options or
  cancelling everything. Do not add one.

Tests against recorded responses: field mapping; the mode guard; the
duplicate path; a rejected order maps to `rejected` with the broker's
reason; headers are never logged.

### M09-T07 Ledger

`ledger.py`. An entry: `id`, `ts`, `type`, `symbol`, `quantity`,
`price`, `amountUsd` (signed effect on cash), `synthetic` (true when
the broker did not produce it), `source`, `orderId`, `note`.

Entry types: `opening_balance`, `buy`, `sell`, `dividend`,
`dividend_withholding`, `margin_interest`, `fee`, `running_cost`.

- `open(account)`: one `opening_balance` entry equal to the broker's
  equity on the first run. This is the only place the capital enters
  the system, and it comes from the broker, not from a file.
- `book_fills(orders)`: one `buy` or `sell` per fill, `source` the
  broker order id. Idempotent on that id.
- `book_dividends(date)`: for each cash dividend with that ex-date and
  each position held at the previous close: `dividend` =
  quantity times cash per share, and `dividend_withholding` = minus
  the rate times that. Synthetic unless T01 showed the paper account
  pays dividends, in which case only the withholding is synthetic.
- `book_interest(date)`: borrowed amount = `max(0, -cash)`. Interest =
  borrowed times `marginRateAnnual / 360`. Synthetic unless T01 showed
  otherwise.
- `book_running_cost(month)`: the month's actual spend from
  `costs.summary()`, synthetic.
- `positions()`, `cash_real()`, `cash_synthetic()`,
  `equity(prices)` = both cash figures plus position values.
- `snapshot(date)`: writes `SNAP#<date>`: equity, cash, gross
  exposure, leverage level, high-water mark, drawdown, day return,
  cumulative index (starts at 100), the three benchmark indexes,
  withholding year to date, estate exposure.

Tests: a full hand-worked week (buy, dividend with withholding,
borrowing with interest, sell) reproduces cash and equity to the cent;
booking the same fill twice changes nothing; synthetic entries never
enter `cash_real`.

### M09-T08 Tax provision and benchmark

`tax.py`:

- `withholding(gross_dividend, register)`.
- `estate_exposure(us_stock_value, register)`: the amount above the
  exemption run through `tax.estate.brackets`. Fill the brackets from
  the current instructions for IRS Form 706-NA and put the revision
  date in the citation. Status stays `provisional` until the owner's
  adviser confirms (O15). The dashboard labels this line "Contingent
  exposure, not a cost".

`benchmark.py`: from the `SPY` series, three indexes aligned to the
ledger's first day: gross (total return), net (price return plus 70%
of the dividend return), and `BIL` as cash.

### M09-T09 Reconcile

`reconcile.run(broker)`, job `reconcile`:

1. Pull orders and activities since the last run. Update order
   statuses. Book fills.
2. Book dividends and interest for the session.
3. Compare: each symbol's quantity in the ledger and at the broker
   must be equal; `ledger.cash_real()` and the broker's cash must
   agree within one US dollar.
4. Write the snapshot.
5. On any difference: put the details on the job run row and finish
   it with status `failed_mismatch`. M11 turns this into a breaker.

Tests with `FakeBroker`: clean; a quantity difference; a cash
difference; a fill that arrives a day late is booked once.

### M09-T10 Jobs, API, dashboard

Jobs: `portfolio_propose` (manual and called by `monthly_rebalance`
after the committee; writes the target and `proposed` orders),
`reconcile` (scheduled), `broker_setup` (manual; `configure()` and
`ledger.open`), `broker_smoke` (manual; buys one share of `SPY`, waits
for the fill on the next reconcile; needs `TradingEnabled`),
`leverage_overlay` (manual).

Routes (red: ask first): `GET /portfolio/summary`,
`GET /portfolio/positions`, `GET /portfolio/history`, `GET /ledger`.
Schedule `findingalpha-reconcile`.

`PortfolioPage.tsx`:

- KPI tiles: equity index (starts at 100), return since start against
  SPY net and SPY gross, leverage level and gross exposure, drawdown.
  Amounts in US dollars are shown only on this private page and are
  never logged or written to git.
- Chart: portfolio index, SPY net, SPY gross.
- Positions table: symbol, sector, weight, target weight, return since
  purchase, thesis link.
- Proposed orders of the latest batch with their reasons.
- Costs and tax card: withholding year to date, margin interest year
  to date, running cost year to date, the contingent estate line.
- Reconcile status with the time of the last clean run.

Nav entry "Portfolio" (`bi-pie-chart`), mock fixtures, unit tests,
smoke test line.

### M09-T11 First run on paper

Needs `TradingEnabled=true` and the runtime switch on.

1. `broker_setup`. The Portfolio page shows the opening balance.
2. `broker_smoke`. After the next `reconcile` the ledger shows one
   share of `SPY` and reconcile is clean. Sell it with a second smoke
   run (`side: sell`) so the account is flat again.
3. `portfolio_propose`. Read the proposed orders with the owner. Check
   three by hand against the rules.
4. Turn `TradingEnabled` off again until M10 is merged.

## Done when

- Engine unit tests pass, including the random-batch test in T02.
- `rg -n "api.alpaca.markets" backend/` shows only the paper host and
  the data host.
- The smoke test round trip reconciled cleanly.
- The leverage memo is merged and the owner replied.
- The Portfolio page shows the opening balance, the benchmark lines
  and the proposed orders.

## Rollback

`TradingEnabled=false` and redeploy. Revert. Ledger rows stay. A paper
account can be reset from the Alpaca dashboard by the owner. A reset
breaks the match between ledger and broker, so stop and ask first. The
old ledger rows are kept, never deleted.

## Open questions

- The owner's confirmation of the provisional portfolio numbers
  (12 to 20 names, 8% and 10% caps, 25% sector, 25% monthly turnover).
- What Alpaca paper simulates (T01).
- The estate-tax schedule and whether cash at a US broker counts (O15).
