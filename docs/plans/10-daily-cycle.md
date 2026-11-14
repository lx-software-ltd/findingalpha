# Plan: M10 daily cycle

**Status**: Draft
**Zone**: red (`holds.py`, order submission, SES policy, schedules,
routes)

## Goal

The system runs by itself on paper. Every US session it checks whether
anything must change, tells the owner by email at 07:30 Hong Kong
time, and executes at 09:45 New York time whatever the owner did not
veto. Once a month it rebalances. Most days the email says "No action
today".

## Non-goals

- No real money and no approvals flow. Approvals are described here
  only so the record types stay separate.
- No intraday trading, no limit orders, no retry of an unfilled order
  on the same day.
- No model writing the email. The brief is built by code from records.
- No amounts of money in the email. The email shows weights and
  percentages and links to the dashboard.
- No "un-veto".

## Files

```
backend/lambda/engine/daily_check.py   test_daily_check.py
backend/lambda/engine/holds.py         test_holds.py         (red)
backend/lambda/engine/brief.py         test_brief.py
backend/lambda/engine/brief_email.py   test_brief_email.py
backend/lambda/engine/orders.py        (continue_batch; red)
backend/lambda/engine/committee.py     (event triage, single-name debate)
backend/lambda/engine/jobs_handler.py  api_handler.py
contracts/methodology.json  contracts/budgets.json  contracts/jobs.json   (red)
backend/infrastructure/lib/schedules.ts  api-routes.ts  functions.ts  ses-send.ts   (red)
apps/admin_web/src/pages/HoldsPage.tsx  BriefsPage.tsx   (+ nav, mock, tests)
docs/deployment/runbook.md
```

## Invariants this change preserves

- A hold executes only when all of these are true at execution time:
  status `pending`, execution time reached, `TradingEnabled` on in both
  places, no blocking breaker, market open, `limits.check_batch` clean.
- A veto is a conditional update from `pending` to `vetoed`. It is
  audited. It cannot be undone.
- Orders are sent only by `EngineFn`. `AdminApiFn` can veto and read.
- Buys of a batch are sent only after its sells have reached a final
  state.
- The email is sent at most once per brief.
- Everything in the email is HTML-escaped. The dashboard shows the
  brief from JSON, never from stored HTML.
- A daily model verdict alone never sells. It can only start a full
  three-role debate on that one company.

## Register and budget additions

```json
"execution": {
  "holdExecuteTime": "09:45",
  "holdExecuteTimeZone": "America/New_York",
  "holdExpiresAfterSessions": 5,
  "maxPriceMoveSinceProposal": 0.10
},
"exits": {
  "reviewAtLossFromCost": 0.25,
  "maxSingleNameDebatesPerDay": 3
}
```

`contracts/budgets.json`: `llm.maxOutputTokens.triage = 300`.

## How a day goes

Times are Hong Kong unless stated. Example for a Monday US session.

| Time | Job | What happens |
| --- | --- | --- |
| Tue 06:00 | `ingest_daily` | Monday's prices, corporate actions, filings, news |
| Tue 06:30 | `reconcile` | Fills, dividends, interest, comparison with the broker, snapshot |
| Tue 06:40 | `daily_check` | Rules below. May create orders and holds |
| Tue 07:15 | `brief_compile` | Builds the brief record |
| Tue 07:30 | `brief_send` | Sends the email |
| Tue 09:45 New York (21:45 or 22:45 Hong Kong) | `execute_holds` | Sends the sells of every hold that was not vetoed |
| every 15 min | `tick` | Sends the buys of a batch once its sells are final |
| Tue 16:30 New York | `post_trade` | Updates order statuses, books fills, closes holds |

So the owner has about fourteen hours between the email and the
execution. After a monthly rebalance (Saturday) the window is two days.

## Steps

### M10-T01 Holds

`holds.py`. One hold per order. Fields: `holdId`, `orderId`,
`batchId`, `symbol`, `side`, `weightChange`, `reason`, `thesisId`,
`executeAt`, `status`, `createdAt`, `vetoedAt`, `vetoNote`.

Statuses: `pending`, `vetoed`, `executing`, `executed`, `not_filled`,
`blocked`, `expired`.

- `create_for_batch(batch_id, session_calendar)`: for each `proposed`
  order, write a hold with `executeAt` = the next session's
  `holdExecuteTime`, and move the order to `held`.
- `veto(hold_id, user_sub, note)`: conditional update
  `pending -> vetoed`; order `held -> vetoed`; audit row. A second veto
  returns the stored state. A veto after execution has started returns
  409.
- `due(now)`: pending holds with `executeAt <= now`, grouped by batch.
- `expire_old(now)`: a pending hold more than
  `holdExpiresAfterSessions` sessions past `executeAt` becomes
  `expired`.

An **approval** is a different record (`APPROVAL#...`) that executes
only on a yes. Nothing creates one in this milestone. Do not add a
flag to holds that makes them behave like approvals.

Tests: the next-session calculation over a weekend and over a US
holiday; veto is idempotent; veto loses the race against execution;
expiry.

### M10-T02 Daily check

`daily_check.run(date)`, after `reconcile`. If the last reconcile was
not clean, do nothing and record `skipped_reconcile`. Otherwise, in
this order:

1. **Machine kill criteria.** For each active thesis, evaluate each
   kill criterion against the newest factor snapshot. If one is met:
   thesis status `broken`, with the criterion and the value. Intent:
   sell the whole position. Reason `thesis_exit`.
2. **Hard position limit.** A position above `maxPositionWeightHard`:
   intent to sell down to `maxPositionWeightAtBuy`. Reason
   `risk_trim`.
3. **Leverage.** `leverage.target_level(..., is_rebalance=False)`.
   - If the level drops to 1.0: intents that sell every position in
     the same proportion until exposure is `1.0 - cashBufferWeight`.
     Reason `leverage_step_down`. Store the new level.
   - Else if exposure is above the level by more than
     `trimWhenAboveLevelBy`: the same proportional sale down to the
     level. Reason `risk_trim`.
4. **Buy halt.** Set or keep the buy halt when drawdown is at or
   beyond `haltBuysAtPortfolioDrawdown` (M11 makes it a breaker).
5. **Watch list**, no orders:
   - a position down `reviewAtLossFromCost` or more from its average
     cost;
   - a held company that filed an 8-K since the last check;
   - a held symbol missing from the newest universe or without a price
     for the session.
6. **Event triage** (needs `CommitteeEnabled`). For each held company
   with a new 8-K or five or more new news items: one cheap model call
   with the thesis and the new items, returning
   `{"assessment": "intact" | "weakened" | "broken", "reason", "refs"}`.
   Validate it like committee output.
7. **Single-name debate.** For each `broken` assessment, up to
   `maxSingleNameDebatesPerDay`: run analyst, bear and chair on that
   one company through `committee.run_single(symbol)`. A chair `avoid`
   gives thesis status `exit` and an intent to sell. `weakened` only
   goes on the watch list.
8. Merge intents per symbol (the largest sale wins). `orders.propose`,
   then `holds.create_for_batch`.

Rules 1 to 5 are code only and run even when the model budget is used
up or `CommitteeEnabled` is off.

Tests with `FakeBroker` and a fake model: each rule alone; no intents
on a quiet day; an unclean reconcile skips everything; a `broken`
triage without a chair `avoid` sells nothing; merged intents never
sell more than is held.

### M10-T03 Monthly rebalance, complete

`monthly_rebalance` (first Saturday 08:00) becomes a chain of stages
saved in its job cursor, resumed by `tick`:

1. `screen` for the last session.
2. `committee.run`.
3. Leverage level with `is_rebalance=True`.
4. `portfolio.build_target` and `portfolio.diff`.
5. `orders.propose` and `holds.create_for_batch` (execution on the
   next session, normally Monday).
6. A brief of kind `rebalance`, compiled and sent when stage 5 ends.

If the committee stopped on budget, stage 4 uses the theses that
exist, and the brief says how many companies were not reviewed.
If a daily batch for the same symbols is still pending, the rebalance
batch replaces it: the older holds become `expired` with the note
`superseded`.

### M10-T04 Execution

`execute_holds` (09:45 New York, Monday to Friday):

1. `broker.clock()`. Market closed (holiday): move `executeAt` of the
   due holds to the next session and stop.
2. `holds.expire_old`.
3. For each batch with due holds:
   1. Stop with `blocked` if a blocking breaker is set, if the newest
      price file is older than the previous session, or if the kill
      switch is off.
   2. Price check: a **buy** whose last price moved more than
      `maxPriceMoveSinceProposal` from its reference price becomes
      `blocked`. Sells are not blocked by price.
   3. Recompute buy quantities from the current equity and price,
      never above the proposed quantity.
   4. `orders.submit_batch` for the sells. Holds become `executing`.
   5. Mark the batch `sells_submitted`.

`orders.continue_batch(batch_id)`, called by `tick` during market
hours: when every sell of the batch is final, run
`limits.check_batch` on the buys with fresh account data and submit
them. If the check fails, the buys become `blocked`. After 15:30 New
York nothing new is submitted.

`post_trade` (16:30 New York): update statuses, `ledger.book_fills`,
set each hold to `executed` or `not_filled`. An order that did not
fill is not retried. It appears in the next brief.

Tests: holiday; kill switch off; a vetoed sell and a remaining buy
that then fails the limits; the price-move block; buys wait for sells;
running `execute_holds` twice submits once.

### M10-T05 Brief

`brief.compile(date, kind)` builds a JSON document from records only.
Kinds: `daily`, `rebalance`. Sections, each a list of plain items:

1. `headline`: "No action today" or "3 orders planned for Tuesday
   09:45 New York time".
2. `planned`: per hold: symbol, company name, side, weight before and
   after, reason in one sentence, thesis link, hold link.
3. `executed`: yesterday's fills and anything not filled, blocked or
   vetoed.
4. `portfolio`: return since start and this month against SPY net and
   SPY gross, leverage level, gross exposure, drawdown, number of
   positions. Percentages only.
5. `watch`: the watch list, triage results, broken theses.
6. `system`: failed jobs, breakers, switches that are off, model and
   knowledge base spend against the caps, days of paper trading.
7. `rebalance` (that kind only): counts per committee decision, names
   entering and leaving with the first two sentences of each thesis.

A day with no US session the day before: `brief_compile` records
`skipped_no_session` and nothing is sent.

Stored as `BRIEF#<date>` / `DAILY` or `REBALANCE` and at
`briefs/date=<date>/<kind>.json`.

`brief_email.py`:

- `subject(brief)`: `findingalpha 2026-11-17: no action` or
  `findingalpha 2026-11-17: 3 orders planned`.
- `render_text(brief)` and `render_html(brief)`: a single-column
  layout with inline styles, no images, no scripts. Every value goes
  through `html.escape`. Links point only at `ADMIN_WEB_ORIGIN`.
- `send(brief)`: first a conditional update that sets `sendStartedAt`
  if it is absent, then `sesv2.send_email` from
  `<BRIEF_FROM_LOCAL_PART>@<MAIL_SENDING_DOMAIN>` to
  `BRIEF_RECIPIENT_EMAIL`, then `sentAt` and the SES message id.
  Skipped with a recorded reason when the domain or recipient setting
  is empty or `BriefEmailEnabled` is off.

Tests: a quiet day; a day with orders; escaping of a company name with
`<` and `&`; a thesis text containing a script tag appears as text;
the second `send` does not send; the recipient address never appears
in a log line.

### M10-T06 Infrastructure (red: ask first)

- `ses-send.ts`: copy `sesSendFromDomainStatement` from `lx-software`.
  Attach it to `EngineFn` only, behind a CloudFormation condition that
  `MailSendingDomain` is not empty. The SES identity itself is created
  by the owner (O16), not by the stack.
- Schedules: `daily-check`, `brief-compile`, `brief-send`,
  `execute-holds`, `post-trade`, with the crons and time zones in
  `reference.md` section 9.
- Routes: `GET /holds`, `POST /holds/{holdId}/veto`, `GET /briefs`,
  `GET /briefs/{date}`.
- Jest: the SES statement has the `ses:FromAddress` condition; the two
  New York schedules carry `America/New_York`; `AdminApiFn` has no SES
  permission and cannot read either secret.

### M10-T07 Dashboard

`HoldsPage.tsx`:

- **Pending**: one card per batch. Each hold: symbol, side, weight
  change, reason, thesis link, time left until execution in the
  owner's local time and in New York time. A **Veto** button opens a
  confirmation dialog with an optional note. After a veto the row
  shows "Vetoed" at once and the list is fetched again.
- A line above a risk sale (`leverage_step_down`, `risk_trim`,
  `thesis_exit`): "This sale reduces risk. If you veto it, the same
  rule will propose it again tomorrow."
- **History**: the last 90 days with final status.

`BriefsPage.tsx`: list by date; a brief renders from its JSON with the
same sections as the email.

Nav entries "Holds" (`bi-hourglass-split`, with a count badge of
pending holds) and "Briefs" (`bi-envelope`). Mock fixtures for a quiet
day and a rebalance day. Unit tests for the veto flow, including the
409 case. Smoke test lines.

### M10-T08 Runbook

`docs/deployment/runbook.md`, written for the owner:

- how to stop everything (the Settings switch, then the stack
  parameter);
- how to veto;
- what each hold status and each brief section means;
- what to do when no email arrived on a session day;
- how to start a job by hand and which jobs may be started.

### M10-T09 Go live on paper

Needs O16. In this order, one change per deploy or settings change:

1. `BriefEmailEnabled` on. Three mornings of "No action today" briefs
   arrive and read correctly.
2. `TradingEnabled` on, `LeverageEnabled` off. Start
   `monthly_rebalance` by hand on a weekend. Read the holds with the
   owner. Veto one on purpose.
3. After the next session: the vetoed order did not trade, the others
   filled, `reconcile` is clean, the brief reports all of it.
4. Record the first day of paper trading in the gate record (M11 reads
   it).

## Done when

- Engine and web unit tests pass.
- Steps 1 to 3 of T09 happened on the deployed system and are written
  up in the pull request with dates.
- Five sessions in a row ran every scheduled job without failure.

## Rollback

`TradingEnabled=false` stops executions. Pending holds stay pending
and expire. `BriefEmailEnabled=false` stops email. Revert the pull
request for code. Orders already filled on paper stay in the ledger.

## Open questions

- Whether the owner wants the email on days without a US session
  ("market closed, nothing to do"). The plan sends nothing.
- Whether a veto of a risk sale should need a typed reason.
