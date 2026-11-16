# Plan: findingalpha build overview

**Status**: Draft
**Zone**: red (most milestones touch infrastructure, contracts or money paths)

This file is the map. A developer who has never seen the project should
read it fully before opening any milestone file.

## 1. What we are building

A system for one owner that:

1. Keeps a knowledge base of the owner's finance books and papers. The
   knowledge base holds the theory: formulas, rules, logic.
2. Every month, scores about 1,000 to 1,500 liquid US stocks with tested
   formulas, shortlists about 60, and has a committee of language models
   argue for and against each one, citing the knowledge base.
3. Holds 12 to 20 positions with position and sector limits, and uses
   borrowed money (leverage) only under strict rules.
4. Checks every day whether anything must change, and sends one email at
   07:30 Hong Kong time saying what to buy and sell, and why.
5. Places the orders on a paper (pretend-money) broker account. Real
   money comes later, after a gate is passed.
6. Shows everything on a private dashboard at `admin.<domain>`.
7. Lets other systems read it and operate it through an HTTP API with
   API keys that carry a tier and scopes.

The target is to beat the S&P 500 after costs and tax. Outperformance
that comes from skill is called alpha.

## 2. Decisions already made by the owner

Do not reopen these. If one looks wrong, raise it in chat.

| Topic | Decision |
| --- | --- |
| Repository | `lx-software-ltd/findingalpha`, public |
| AWS | Same account as `lx-software`, region `ap-southeast-1`, separate stacks |
| CDK bootstrap | Reuse the existing bootstrap with qualifier `siutindei` |
| Database | No RDS. DynamoDB single table and S3 files |
| Knowledge base | Bedrock **Managed** Knowledge Base (hybrid search). Cost must stay capped |
| Knowledge base content | The owner's own PDFs, uploaded by the owner to S3. Plus a journal the system writes |
| Models | Through OpenRouter with a key named `findingalpha` |
| Market | US stocks only |
| Leverage | Hard maximum 1.5 times. Default 1.0 |
| Broker | Alpaca paper account first. Live broker chosen at the gate |
| Data | Free sources: SEC EDGAR, Alpaca market data and news |
| Rhythm | Daily check, rare trades, monthly rebalance |
| Interface | Daily email plus the admin dashboard |
| Dashboard | `admin.<domain>`, Cognito sign-in, same strategy as `admin.lx-software.com` |
| Domain | Registered, DNS on Cloudflare. It stays a setting and is not written in git |
| DNS | Records are created by the developer through the Cloudflare API, in this project's zone only |
| External API | API keys with scopes. Two tiers, `admin` and `user`. Only `admin` is built. Served on `api.<domain>` |
| Stacks | Created from nothing, deployed with the existing `siutindei` bootstrap |
| Cost ceiling | 45 US dollars a month |
| Tax | Ledger books 30% dividend withholding and shows an estate-tax exposure line |
| Deferred | X/Twitter feeds, paid earnings-call transcripts |

## 3. Rules that never bend

These are the invariants. Every milestone file repeats the ones it
touches. A pull request that breaks one is rejected.

1. **Three layers.** Theory lives in the knowledge base. Every formula
   and threshold the code uses is written in
   `contracts/methodology.json` with a citation. Code implements the
   register and is unit-tested. A language model never computes a number
   that decides money. It reads, argues, cites and proposes.
2. **Leverage cap in code.** No order may leave gross exposure above
   1.5 times equity, whatever the register or a model says. If falling
   prices push exposure above the target, the daily check sells down.
3. **Never available to the system:** withdrawals, options, short
   selling, changing its own limits.
4. **Paper only until the gate.** The broker code refuses any host other
   than the paper host. The stack parameter `BrokerMode` only allows
   `paper`.
5. **Kill switches fail closed.** A missing or unreadable switch means
   off.
6. **Holds and approvals are different things.** A hold runs unless the
   owner says no. An approval runs only if the owner says yes. Paper
   orders are holds. Real-money orders start as approvals.
7. **No model call inside an HTTP request.** API Gateway cuts requests
   at 30 seconds. Long work runs as a job with a DynamoDB job row and
   the page polls.
8. **Every model call goes through `openrouter_client.py`** with data
   collection denied, and is counted against a daily budget.
9. **No secrets in git.** Secret stack parameters use `noEcho: true`.
   Keys live in Secrets Manager.
10. **No personal data in git.** No real names, emails, phones,
    addresses, account numbers. Tests use invented people and
    `example.com`. The capital amount and holdings never appear in the
    repository.
11. **Shared constants live in `contracts/*.json`** and are synced with
    `python3 scripts/sync-contracts.py`.
12. **Every order traces to a thesis record with citations.**
13. **API keys are limited.** Only the scrypt digest of a key is
    stored. A key has a tier, scopes and an expiry, and is read-only
    unless both the key and the stack allow writes. No key can turn a
    switch on, reset a breaker, approve an order or manage keys.

## 4. Architecture

```
                 owner
        +----------+-----------+
        | browser              | email 07:30 HKT
        v                      ^
 CloudFront + S3 (SPA)         |
 admin.<domain>                |
        |  Cognito ID token    |
        v                      |
 API Gateway HTTP API          |
        |                      |
        v                      |
 AdminApiFn (reads, vetoes) ---+-----------------+
        |                                        |
        v                                        |
 DynamoDB single table  <----  EngineFn (jobs) --+--> SES
 S3 data bucket         <----     ^   |  |  |
                                  |   |  |  +--> Alpaca paper API
        EventBridge Scheduler ----+   |  +-----> OpenRouter
                                      +--------> Bedrock Managed KB
                                      +--------> SEC EDGAR, Alpaca data
 S3 KB bucket (owner PDFs) ---> Bedrock Managed KB
```

- **Two stacks.** `findingalpha` (everything except web hosting) and
  `findingalpha-admin-web` (S3 + CloudFront for the dashboard).
- **Two Lambda functions from one code folder** (`backend/lambda/engine`).
  `AdminApiFn` serves the dashboard and holds no broker or model keys.
  `EngineFn` runs scheduled jobs and holds those keys. Two small
  functions guard the doors: `PreTokenGenerationFn` for sign-in and
  `PublicApiKeyAuthorizerFn` for API keys.
- **One DynamoDB table** with `pk`/`sk` and one index `gsi1`. Price and
  fundamentals history are gzip files in S3.
- **One KMS key** for Lambda environment variables, logs, DynamoDB and
  the dead-letter queue.

All names are in [`reference.md`](reference.md).

## 5. Rhythm (Hong Kong time unless stated)

| When | What |
| --- | --- |
| Tue–Sat 12:00 | Ingest the US session that has closed: prices, corporate actions, filings, news |
| Tue–Sat 06:30 | Reconcile ledger with broker, book dividends and interest, snapshot |
| Tue–Sat 06:40 | Daily check: thesis breaks, risk limits, leverage step-down. May create holds |
| Tue–Sat 07:15 | Compile the brief |
| Tue–Sat 07:30 | Send the brief by email |
| Mon–Fri 09:45 New York | Execute holds that were not vetoed |
| Mon–Fri 16:30 New York | Post-trade reconcile |
| First Saturday 08:00 | Monthly rebalance: screen, committee, target portfolio, holds for Monday |
| First Sunday 10:00 | Monthly review: methodology proposals, gate report, journal entry |
| Sunday 08:00 | Weekly refresh: universe, adjusted price history |
| Daily 05:30 | Knowledge base change check and sync |
| Every 15 minutes | Tick: resume long jobs that saved a cursor |

The two New York schedules use the `America/New_York` time zone so
daylight saving needs no code.

## 6. Cost budget (US dollars a month)

| Item | Budget | How it is held |
| --- | --- | --- |
| AWS base (KMS key, secrets, Lambda, DynamoDB, S3, CloudFront, logs, SES) | 8 | Small by design. No NAT, no VPC, no RDS |
| Managed Knowledge Base | 15 | 5 per GB stored, 1 per 1,000 retrievals. Hard caps: 2 GB, 5,000 retrievals a month |
| Models through OpenRouter | 22 | 1 a day, 8 on rebalance day, 25 a month. Refuse when reached |
| Market data | 0 | SEC EDGAR and Alpaca free plan |
| **Total** | **45** | Running cost is booked in the performance report |

A new WAF web ACL costs about 5 a month. Reuse the existing global web
ACL from `lx-software` if there is one, or leave it off.

## 7. Milestones

| Id | Milestone | File | Zone | Needs from owner |
| --- | --- | --- | --- | --- |
| M01 | Agent harness and repository skeleton | [01](01-agent-harness.md) | red | PII denylist hashes, branch protection |
| M02 | Infrastructure skeleton | [02](02-infrastructure-skeleton.md) | red | Domain, GitHub environment, certificate, Google client |
| M03 | Admin dashboard v1 | [03](03-admin-dashboard.md) | yellow | DNS record |
| M03A | External API with keys and scopes | [03a](03a-external-api.md) | red | Passphrase secret, first key, API certificate |
| M04 | Data ingest | [04](04-data-ingest.md) | yellow | Alpaca paper keys |
| M05 | Methodology register and factor library | [05](05-methodology-and-factors.md) | red | Review of provisional formulas |
| M06 | Screen and backtest | [06](06-screen-and-backtest.md) | yellow | Read the research memo |
| M07 | Knowledge base | [07](07-knowledge-base.md) | red | PDFs uploaded, 20 test questions |
| M08 | Investment committee | [08](08-investment-committee.md) | yellow | OpenRouter key |
| M09 | Portfolio, ledger, paper broker | [09](09-portfolio-ledger-broker.md) | red | Tax figures confirmed |
| M10 | Daily cycle | [10](10-daily-cycle.md) | red | SES identity |
| M11 | Safety and go-live gate | [11](11-safety-and-go-live-gate.md) | red | Run the drill |
| M12 | Real money | outline in [11](11-safety-and-go-live-gate.md) | red | Separate approval |

Order and dependencies:

```
M01 -> M02 -> M03 -> M04 -> M05 -> M06
               |       \            \
               |        +-> M07 -----+-> M08 -> M09 -> M10 -> M11 -> (M12)
               +-> M03A
```

M03 comes early on purpose. From that point the owner follows progress
on the dashboard. M03A follows M03 and blocks nothing: later milestones
only have to give each new route a key scope. M07 can start as soon as
M02 is deployed and the PDFs are uploaded. It does not wait for M06.

The first deploy needs the certificate and the GitHub variables and
secrets listed in [`owner-checklist.md`](owner-checklist.md).

## 8. How to work on a milestone

Follow this every time.

1. Read this file, [`reference.md`](reference.md) and the milestone file.
2. Check the zone. **Red:** post a short message in chat that names the
   milestone and the files, and wait for the owner to say go. Do not
   write anything before that. **Yellow:** the milestone file is the
   plan. Write tests first.
3. Check [`owner-checklist.md`](owner-checklist.md). If an item that
   blocks the milestone is open, ask the owner. Do not work around it.
4. Create a branch from `main`. One milestone may be several pull
   requests. Keep each under about 800 changed lines when possible.
5. For each step in the file, in order: write or update the test, write
   the code, run the check named in the step.
6. Before pushing, run the `verify-change` skill (created in M01). At
   minimum:
   - `python3 -m ruff check backend/lambda scripts .cursor/hooks`
   - `python3 -m unittest discover -s backend/lambda/engine -p 'test_*.py'`
   - `python3 scripts/check-contracts.py`
   - `python3 scripts/validate_agent_rules.py`
   - `python3 scripts/check_file_length.py`
   - `python3 scripts/check_test_focus.py`
   - `python3 scripts/check_pii.py`
   - In `apps/admin_web`: `npm run lint`, `npm test`, `npm run build`
   - In `backend/infrastructure`: `npm run build`, `npm test`
7. From M03A on: a new dashboard route gets a key scope or is marked
   owner only, in the route table and in `reference.md` section 8. A
   new job gets a `keyRun` decision.
8. In the same pull request, set the finished steps to `done` in
   `contracts/roadmap.json` and run `python3 scripts/sync-contracts.py`.
9. Fill in the pull request template: Intent, Zone, Invariants,
   Evidence, Docs and contracts, Rollback.
10. Never run `cdk deploy`, `cdk destroy` or an `aws delete-*` command.
    Deploys happen from GitHub Actions after merge. Never push to `main`.

### Stop and ask

Stop and ask the owner in chat when:

- a step would touch a red path that the milestone file does not list;
- a formula or threshold is needed that is not in the register;
- a check in a step fails and the fix is not obvious within the step;
- an external service behaves differently from what the plan says
  (prices, limits, request shapes);
- anything would put capital, holdings, names, emails, account ids or
  the domain into git;
- a DNS record is about to be created or changed;
- the monthly cost estimate would pass the ceiling.

### Where to copy from

The plan says "copy from `lx-software`" often. That means the
repository `lx-software-ltd/lx-software`, read at commit
`09db6682498aa8f22e0be8bca95576976a504f83`. Copy the file, then rename
`lxsoftware`, `lx_admin` and `lx-software` identifiers as the step says.
Do not improve the copied code in the same pull request. If the current
`lx-software` file differs from what a step describes, the sibling file
wins for style and the plan wins for names.

## 9. Glossary

| Term | Meaning |
| --- | --- |
| Alpha | Return above the benchmark that is not explained by simply holding the market |
| Benchmark | SPY, the S&P 500 fund. Shown gross and net of 30% dividend withholding |
| Universe | The list of stocks the screen is allowed to look at |
| Factor | A number computed for each stock, such as return on invested capital |
| Screen | Scoring the universe with factors and keeping the best |
| Point in time | Using only data that was public on the date being simulated |
| Thesis | The written reason for owning a stock, with conditions that would end it |
| Kill criterion | A condition that ends a thesis, such as debt rising above a limit |
| Leverage | Buying more stock than the account's own money by borrowing from the broker |
| Gross exposure | Value of all positions divided by the account's own money |
| Drawdown | Fall from the highest account value so far, in percent |
| Hold | An action that runs at a set time unless the owner vetoes it |
| Approval | An action that runs only after the owner says yes |
| Breaker | An automatic stop that trips on a bad condition and needs a manual reset |
| Kill switch | A manual on/off setting for a whole capability |
| Register | `contracts/methodology.json`, the list of formulas and thresholds with citations |
| KB | The Bedrock Managed Knowledge Base |
| Paper | A broker account with pretend money and real prices |
| Gate | The list of conditions that must hold before real money |

## Open questions

- Whether an existing global WAF web ACL can be shared.
- Whether the dashboard should also show Hong Kong dollar values. Not
  planned. Add later if wanted.
