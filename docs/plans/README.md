# Plans

A yellow-zone change starts as a short plan copied from
[`_template.md`](_template.md).
Red-zone work is planned in chat and waits for an explicit approval
before any write. The zone map is
[`docs/architecture/zones.md`](../architecture/zones.md).

## The build plan

The numbered files are the build plan for the whole system. Read them in
order. Each milestone is one or more pull requests.

| File | What it covers |
| --- | --- |
| [`00-overview.md`](00-overview.md) | What we build, decisions, rules, architecture, cost, milestone order, how to work |
| [`reference.md`](reference.md) | Names, parameters, data model, storage layout, routes, schedules. Look things up here |
| [`owner-checklist.md`](owner-checklist.md) | Everything only the owner can do, and which milestone it blocks |
| [`01-agent-harness.md`](01-agent-harness.md) | Rules, zones, hooks, checks, CI |
| [`02-infrastructure-skeleton.md`](02-infrastructure-skeleton.md) | CDK stacks, sign-in, API, web hosting, deploy workflows |
| [`03-admin-dashboard.md`](03-admin-dashboard.md) | The dashboard on `admin.<domain>` behind Cognito |
| [`03a-external-api.md`](03a-external-api.md) | API keys with tiers and scopes for other systems |
| [`04-data-ingest.md`](04-data-ingest.md) | Universe, prices, fundamentals, news |
| [`05-methodology-and-factors.md`](05-methodology-and-factors.md) | Methodology register and the factor library |
| [`06-screen-and-backtest.md`](06-screen-and-backtest.md) | The numeric screen and the 2016–2026 backtest |
| [`07-knowledge-base.md`](07-knowledge-base.md) | Bedrock Managed Knowledge Base, sync, retrieval, MCP |
| [`08-investment-committee.md`](08-investment-committee.md) | The model committee, budgets, thesis journal |
| [`09-portfolio-ledger-broker.md`](09-portfolio-ledger-broker.md) | Portfolio rules, leverage, ledger, tax provision, paper broker |
| [`10-daily-cycle.md`](10-daily-cycle.md) | Holds, order execution, the daily email, dashboard pages |
| [`11-safety-and-go-live-gate.md`](11-safety-and-go-live-gate.md) | Breakers, the drill, the gate report, real-money outline |

Every numbered milestone file uses the headings of
[`_template.md`](_template.md) and
adds a **Steps** section. Steps have ids such as `M03-T05`. The
dashboard's Roadmap page shows those ids, so do not renumber them.

## Other plans

| File | What it covers |
| --- | --- |
| [`data-precision-followups.md`](data-precision-followups.md) | Follow-ups on data precision |

## Status values

`Draft` (not approved), `Approved` (owner said go in chat), `In progress`,
`Done`. Change the status line in the same pull request that changes
the work.
