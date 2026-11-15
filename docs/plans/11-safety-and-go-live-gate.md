# Plan: M11 safety and go-live gate (and M12 outline)

**Status**: Draft
**Zone**: red (`breakers.py`, `gate.py`, `contracts/gate.json`, routes)

## Goal

Two things. First, automatic stops (breakers) that halt trading when
something is wrong and stay tripped until the owner resets them, proven
by a drill. Second, a gate report that says, from recorded evidence,
whether the system is ready for real money. The report advises. Only
the owner decides.

## Non-goals

- No real money. M12 is an outline at the end of this file and needs
  its own plan and approval.
- No automatic reset of a breaker.
- No paging service. Alerts go by email through the path M10 built.
- The gate does not require the paper account to have made money. Six
  months of returns prove little. The gate tests whether the machine
  is reliable and honest.

## Files

```
contracts/gate.json                      (red)
backend/lambda/engine/breakers.py   test_breakers.py   (red)
backend/lambda/engine/gate.py       test_gate.py       (red)
backend/lambda/engine/orders.py  daily_check.py  reconcile.py  brief.py  system_status.py
backend/lambda/engine/jobs_handler.py  api_handler.py
backend/infrastructure/lib/api-routes.ts   (red)
apps/admin_web/src/pages/GatePage.tsx  RoadmapPage.tsx   (+ nav, mock, tests)
docs/deployment/runbook.md   docs/research/drill-<date>.md
```

## Invariants this change preserves

- A breaker that cannot be read counts as tripped.
- Tripping is automatic. Resetting is a signed-in owner action with a
  written note, audited, and refused while the cause is still present.
- Breakers and kill switches are separate. A switch is the owner's
  choice. A breaker is the system's alarm. Trading needs both clear.
- Gate criteria live in `contracts/gate.json`. Changing one is a
  red-zone pull request.
- `BrokerMode` still only allows `paper`.

## Breakers

| Name | Trips when | Blocks | Reset allowed when |
| --- | --- | --- | --- |
| `ledger_mismatch` | `reconcile` finds a quantity or cash difference | all orders | the newest reconcile is clean |
| `data_stale` | at execution time the newest price file is older than the previous session, or more than 2% of universe prices failed quality checks | all orders | the newest ingest is complete |
| `order_rejects` | three or more orders rejected by the broker in one session | all orders | the owner has read the reasons |
| `exposure_breach` | gross exposure above 1.5 plus 0.10 at reconcile on two sessions in a row | buys | exposure is at or below the level |
| `drawdown_halt` | drawdown at or beyond `haltBuysAtPortfolioDrawdown` | buys | the owner chooses. The note must say why |
| `job_failures` | `reconcile`, `daily_check` or `execute_holds` failed three times in a row | all orders | the job's newest run succeeded |

"Blocks buys" leaves sales running, because sales lower risk.
`ledger_mismatch` blocks sales too: when the books are wrong the system
does not know what it holds.

## Steps

### M11-T01 Breaker module

`breakers.py`. Record `BREAKER#<name>` / `STATE`: `tripped`, `scope`
(`all` or `buys`), `trippedAt`, `reason`, `details`, `resetAt`,
`resetBy`, `resetNote`, and a `history` list capped at 20 entries.

- `trip(name, reason, details)`: conditional write. Tripping a breaker
  that is already tripped changes nothing. Sends one alert email
  (T03).
- `blocking(side)`: names of tripped breakers that block that side.
  Any read error returns `["unreadable"]`.
- `can_reset(name)`: evaluates the "reset allowed when" column and
  returns `(ok, why_not)`.
- `reset(name, user_sub, note)`: requires a note of at least 10
  characters and `can_reset`. Audit row.
- Names and scopes come from a constant table in the module. An
  unknown name raises.

Tests: fail closed on a read error; trip is idempotent; reset is
refused while the cause remains; reset needs a note; scope `buys` does
not block a sell.

### M11-T02 Wire the breakers in

- `reconcile.run`: mismatch trips `ledger_mismatch`. Exposure above
  1.60 on two sessions running trips `exposure_breach`.
- `daily_check`: the buy halt of M10 becomes `drawdown_halt`.
- `orders.submit_batch` and `orders.continue_batch`: call
  `breakers.blocking(side)` immediately before each submission, not
  once per batch.
- `execute_holds`: stale data trips `data_stale`.
- `post_trade`: counts rejections and trips `order_rejects`.
- `job_runs.record`: on the third failure in a row of a listed job,
  trips `job_failures`.
- `system_status` and the brief `system` section list tripped
  breakers first.

Each of these has a test that the trip happens and that no order is
submitted afterwards.

### M11-T03 Alerts

`brief_email.send_alert(subject, lines)`: a short plain email through
the same sender and recipient, used for: a breaker trip, a brief not
sent by 08:30 Hong Kong time on a session day (checked by `tick`), the
model or knowledge base budget reaching its cap, an API key being
denied (revoked, expired, wrong address), and an API key making a
write. The last two replace the sibling's "Public API key used"
notice. The authorizer keeps its narrow permission: on a denial of a
known key it sets `lastDeniedAt` and `lastDeniedReason` on the key
row, and `tick` sends the alert. A write is reported by `AdminApiFn`
through the job it already may start. At most one alert
per cause per day, kept by a conditional write on
`ALERT#<date>` / `<cause>`. Obeys `BriefEmailEnabled`.

### M11-T04 API and dashboard

Routes (red: ask first): `GET /breakers`,
`POST /breakers/{name}/reset`, `GET /gate`.

`GatePage.tsx`:

- **Breakers**: one row each: state, since when, reason. A tripped row
  has a **Reset** button that opens a dialog with a required note.
  When `can_reset` is false the button is disabled and the reason is
  shown.
- **Gate**: one row per criterion: what it measures, the required
  value, the current value, pass, fail or "not yet measurable", and a
  link to the evidence. A summary line: "7 of 11 passed. Earliest
  possible date: ...".

The phase strip on the Roadmap page now reads `GET /gate`: Build until
M10-T09, Paper trading until every criterion passes, Gate when all
pass, Real money never in this milestone.

### M11-T05 Drill (with the owner, O17)

On the deployed paper system, on a session day, with the owner
present. Write `docs/research/drill-<date>.md` with the time of each
step and what was seen.

1. With a pending hold in place, turn `tradingEnabled` off in
   Settings. At 09:45 New York the hold does not execute and is still
   `pending`. Turn it back on.
2. Veto a hold. It does not execute.
3. Trip `ledger_mismatch` for real: the owner places one manual
   one-share order in the Alpaca paper dashboard. The next `reconcile`
   trips the breaker and the alert email arrives. Try to reset: it is
   refused. Sell the share in the Alpaca dashboard, let `reconcile`
   run clean, then reset with a note.
4. Start the job `breaker_drill` (manual; allowed only while
   `BrokerMode` is `paper`), which trips `data_stale` with the reason
   "drill". Confirm `execute_holds` blocks. Reset.
5. Turn `committeeEnabled` off in Settings. Confirm that the next
   `daily_check` still runs rules 1 to 5 and makes no model call. Turn
   it back on.
6. Turn `TradingEnabled` off as a stack parameter through a normal
   deploy and confirm the runtime switch cannot turn trading back on.

Every step must behave as written. A step that does not is a bug to
fix before the gate can pass. Then repeat the drill.

### M11-T06 Gate contract

`contracts/gate.json`:

```json
{
  "version": 1,
  "criteria": [
    { "id": "paperDays", "min": 180 },
    { "id": "leverageRulesActiveDays", "min": 90 },
    { "id": "jobSuccessRate", "min": 0.95, "windowDays": 180 },
    { "id": "unexplainedReconcileDifferences", "max": 0, "windowDays": 90 },
    { "id": "ordersWithThesisAndCitation", "min": 1.0 },
    { "id": "backtestBeatsNetBenchmark", "equals": true },
    { "id": "monthlyCostWithinBudget", "maxUsd": 45, "months": 3 },
    { "id": "drillPassed", "maxAgeDays": 60 },
    { "id": "provisionalRegisterEntries", "max": 0 },
    { "id": "kbEvaluationPassed", "equals": true },
    { "id": "ownerTasksDone", "through": "O17" }
  ]
}
```

What each one reads:

| Criterion | Evidence |
| --- | --- |
| `paperDays` | Calendar days since the first paper trading day recorded in M10-T09 |
| `leverageRulesActiveDays` | Days with `LeverageEnabled` on. The plan turns it on after the first 90 days |
| `jobSuccessRate` | Scheduled job runs that succeeded, over all that were due. `skipped_disabled` during a planned stop is excluded. A run missing altogether counts as failed |
| `unexplainedReconcileDifferences` | `ledger_mismatch` trips without a reset note that names the cause |
| `ordersWithThesisAndCitation` | Share of submitted orders whose thesis has at least one knowledge base citation. Risk sales count through the thesis of the position |
| `backtestBeatsNetBenchmark` | The M06 run marked as the reference, at the current register hash. A register change after the run makes this "not yet measurable" until it is rerun |
| `monthlyCostWithinBudget` | `costs.summary()` for each of the last three full months |
| `drillPassed` | The drill record written by the manual job `record_drill` with the memo path, after the memo is merged |
| `provisionalRegisterEntries` | Count of register entries whose status is `provisional` |
| `kbEvaluationPassed` | The newest M07 evaluation meets its targets |
| `ownerTasksDone` | Owner tasks O01 to O17 ticked |

Paper performance against SPY net is shown beside the criteria as
information, with the sentence: "Six months is too short to judge
returns. This number does not decide the gate."

### M11-T07 Gate module

`gate.evaluate(date)` returns one result per criterion: `id`,
`status` (`pass`, `fail`, `not_measurable`), `current`, `required`,
`evidence` (record keys or document paths). Stored as `GATE#paper` /
`CHECK#<date>`. Run by `monthly_review` and on `GET /gate` when the
stored check is older than a day.

`gate.phase()`: `build`, `paper`, `gate_ready`. It never returns
`live`.

Tests: one per criterion for pass, fail and not measurable; a register
change invalidates the backtest criterion; a missing job run counts as
a failure.

### M11-T08 Gate report

When every criterion passes, `monthly_review` writes
`journal/<yyyy-mm>-gate-report.md` to the knowledge base bucket and the
brief says so. The report lists each criterion with its evidence, the
paper performance, every breaker trip and veto during the period, and
the open risks from M06 ("known biases") and M09 (tax). It ends with:
"This report does not start real-money trading. That needs the owner's
decision and a separate plan."

## Done when

- Unit tests pass.
- The drill memo is merged and every step behaved as written.
- The Gate page shows every criterion with a current value.
- The owner has reset a real breaker from the dashboard.

## Rollback

Revert the pull request. Without the breaker module the kill switches
still stop trading. Turn `TradingEnabled` off before reverting.

## Open questions

- Whether 180 days is the right length. It is the minimum that
  includes several rebalances, at least one earnings season per
  company twice, and 90 days with leverage rules active.
- Whether the owner wants a second person to read the gate report.

---

# Outline: M12 real money

Not approved. Not planned in detail. Written so that nothing built
before it makes it harder. It starts only after O18.

1. **Separate approval.** A new plan file, red zone, discussed in chat.
2. **Broker.** Decide between Alpaca live (same API as paper, so the
   adapter is reused) and Interactive Brokers (lower margin rates,
   more work). Check at that time: account opening for a Hong Kong
   resident, margin rates, fees, and how each handles the W-8BEN form.
3. **Code changes, each one red:** add `live` to the allowed values of
   `BrokerMode`; a second secret `findingalpha/alpaca-live`; a live
   host constant guarded by the mode; account id `live` in the record
   keys so the paper history stays separate and keeps running beside
   it.
4. **Approvals instead of holds.** Every real-money order needs a yes
   from the owner on the dashboard before it is sent. A hold-style
   default comes only later, if the owner asks for it.
5. **Start small and unlevered.** Leverage 1.0 for at least the first
   three months, a fraction of the capital first, and smaller order
   limits in the register.
6. **Tax and estate.** Act on the adviser's answer from O15 before
   funding. The estate-tax exposure line applies to real holdings
   above the exemption.
7. **Stop conditions agreed beforehand:** the drawdown at which the
   owner wants the system to sell everything and stop, written into
   the register.
8. **The paper account keeps running** on the same rules as a control.
