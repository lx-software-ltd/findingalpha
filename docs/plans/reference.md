# Reference: names, settings, data model

Look things up here. Milestone files point at sections of this file.
When a milestone changes one of these, it changes this file in the same
pull request.

`<domain>` is the owner's domain. It is registered, with DNS on
Cloudflare, and stays a setting. `<account>` and `<region>` are filled
by CloudFormation. None of the three is written in git.

## 1. Repository layout (target)

```
AGENTS.md  BUGBOT.md  SECURITY.md  .cursorrules  pyproject.toml
.cursor/            rules, skills, hooks, environment.json, install.sh, mcp.json
.github/            workflows, PULL_REQUEST_TEMPLATE.md, dependabot.yml
apps/admin_web/     the dashboard (Vite, React, TypeScript, Bootstrap)
apps/public_www/    public logo site (Vite, React, TypeScript)
backend/infrastructure/   CDK app (bin, lib, test, params)
backend/lambda/engine/    all Python for AdminApiFn and EngineFn, tests beside code
backend/lambda/pre_token_generation/   Cognito sign-in gate
backend/lambda/public_api_authorizer/  API key check for /public/* routes
backend/scripts/run-cdk-app.sh
contracts/          JSON sources of truth
docs/architecture/  overview.md, zones.md, security.md
docs/deployment/    setup.md, admin-website.md, knowledge-base.md, runbook.md
docs/plans/         this plan
docs/research/      memos (backtest, KB evaluation)
scripts/            checks, contract sync, deploy helpers, offline tools
```

## 2. Stacks and resource names

| Thing | Name |
| --- | --- |
| Backend stack | `findingalpha` |
| Web stack | `findingalpha-admin-web` |
| Public www stack | `findingalpha-public-www` |
| KMS key alias | `findingalpha/shared` |
| Records table | `findingalpha-records` |
| Audit table | `findingalpha-audit-log` |
| Data bucket | `findingalpha-data-<account>-<region>` |
| Knowledge base bucket | `findingalpha-kb-<account>-<region>` |
| Access logs bucket | `findingalpha-access-logs-<account>-<region>` |
| Web bucket | `findingalpha-web-<account>-<region>` |
| Web logs bucket | `findingalpha-web-logs-<account>-<region>` |
| Public www bucket | `findingalpha-public-www-<account>-<region>` |
| Public www logs bucket | `findingalpha-public-www-logs-<account>-<region>` |
| Public hostname | Apex `<domain>` (canonical). `www.<domain>` 301s to the apex |
| Public response headers | `findingalpha-public-www-security-headers` |
| HTTP API | `findingalpha-admin-api` |
| Dashboard hostname | `admin.<domain>` |
| API hostname for key callers | `api.<domain>` (M03A) |
| Schedules | `findingalpha-<job>` |
| Paper broker secret | `findingalpha/alpaca-paper` |
| OpenRouter secret | `findingalpha/openrouter` |
| Cognito domain prefix | `findingalpha-admin-auth` |
| Response headers policy | `findingalpha-admin-security-headers` |
| API key prefix | `fapk_` |

Both stacks set `Organization` to `LX Software` and `Project` to `Finding Alpha` on the stack and on every resource CloudFormation can tag. `Repository`, `Environment`, and `ManagedBy` stay as they are.

All bucket names stay under 63 characters. Buckets are private
(`BLOCK_ALL`), `enforceSSL`, versioned, `RETAIN`.

## 3. Stack parameters

Keys in `backend/infrastructure/params/production.json` use
`<stack>:<Parameter>`. Values that identify the owner or the account
come from the GitHub `production` environment, not from the file.

### `findingalpha`

| Parameter | Source | Default | Notes |
| --- | --- | --- | --- |
| `AdminWebDomainName` | GitHub var `ADMIN_WEB_DOMAIN_NAME` | none | `admin.<domain>` |
| `GoogleClientId` | GitHub var `ADMIN_GOOGLE_CLIENT_ID` | none | |
| `GoogleClientSecret` | GitHub secret `ADMIN_GOOGLE_CLIENT_SECRET` | none | `noEcho` |
| `AdminFederatedEmailAllowlist` | GitHub secret `ADMIN_FEDERATED_EMAIL_ALLOWLIST` | none | Comma-separated, lower case. Environment `production` |
| `CognitoDomainPrefix` | params file | `findingalpha-admin-auth` | |
| `CognitoCustomDomainName` | GitHub var `ADMIN_COGNITO_CUSTOM_DOMAIN_NAME` | empty | Optional `auth.<domain>`. Empty skips the custom domain. Set with the certificate; both or neither. When set, `CognitoDomain` uses it |
| `CognitoCustomDomainCertificateArn` | production secret `ADMIN_COGNITO_CUSTOM_DOMAIN_CERTIFICATE_ARN` | empty | us-east-1 ACM. Empty skips the custom domain |
| `MailSendingDomain` | GitHub var `MAIL_SENDING_DOMAIN` | empty | `<domain>`. Empty disables email |
| `BriefFromLocalPart` | params file | `brief` | Sender is `brief@<domain>` |
| `BriefRecipientEmail` | GitHub secret `BRIEF_RECIPIENT_EMAIL` | empty | Environment `production` |
| `SecContactEmail` | GitHub secret `SEC_CONTACT_EMAIL` | empty | Goes in the SEC `User-Agent`. Environment `production` |
| `IngestEnabled` | params file | `true` | Kill switch. CDK default stays `false`. The runtime switch must also be on |
| `CommitteeEnabled` | params file | `false` | Kill switch |
| `TradingEnabled` | params file | `false` | Kill switch |
| `LeverageEnabled` | params file | `false` | Kill switch |
| `BriefEmailEnabled` | params file | `false` | Kill switch |
| `BrokerMode` | params file | `paper` | `allowedValues: ["paper"]` until M12 |
| `PublicApiWritesEnabled` | params file | `true` | Kill switch for writes by API key. CDK default stays `false` |
| `ApiCustomDomainName` | GitHub var `API_CUSTOM_DOMAIN_NAME` | empty | `api.<domain>`. Empty skips the custom domain |
| `ApiCustomDomainCertificateArn` | production secret `API_CUSTOM_DOMAIN_CERTIFICATE_ARN` | empty | ACM in `ap-southeast-1`, not us-east-1 |
| `CommitteeAnalystModel` | params file | set in M08 | OpenRouter slug |
| `CommitteeChairModel` | params file | set in M08 | OpenRouter slug |
| `KbMaxRawBytes` | params file | `2147483648` | 2 GB cap |
| `KbMaxRetrievalsPerMonth` | params file | `5000` | |

### `findingalpha-admin-web`

| Parameter | Source | Notes |
| --- | --- | --- |
| `AdminWebDomainName` | GitHub var `ADMIN_WEB_DOMAIN_NAME` | CloudFront alias |
| `AdminWebCertificateArn` | production secret `ADMIN_WEB_CERTIFICATE_ARN` | ACM, us-east-1, ISSUED |
| `CspCognitoConnectOrigin` | Deploy Backend derives it | prefix URL; when custom domain set, also `https://auth.<domain>` (space-separated) | Stack parameter, not an export import |
| `WafWebAclArn` | GitHub var `ADMIN_WAF_WEB_ACL_ARN` | Empty disables |

### `findingalpha-public-www`

| Parameter | Source | Notes |
| --- | --- | --- |
| `PublicWebsiteDomainName` | GitHub var `PUBLIC_WWW_DOMAIN_NAME` | CloudFront alias |
| `PublicWebsiteCertificateArn` | production secret `PUBLIC_WWW_CERTIFICATE_ARN` | ACM, us-east-1, ISSUED |
| `WafWebAclArn` | GitHub var `PUBLIC_WWW_WAF_WEB_ACL_ARN` | Empty disables |

### GitHub variables and secrets

Repository variables (read by `cdk-diff` on pull requests as well):
`AWS_REGION`, `CDK_BOOTSTRAP_QUALIFIER` (`siutindei`), `CDK_PARAM_FILE`
(`backend/infrastructure/params/production.json`). The account id is
the repository variable `AWS_ACCOUNT_ID`. A secret of the same name
still wins. `cdk-diff` passes with a warning and does not compare the
account until that variable and `AWS_REGION` are both set. A
Dependabot pull request can read the variable.

Environment `production`: every "GitHub var" above as a variable. Every
"GitHub secret" above, plus `PUBLIC_API_KEY_GPG_PASSPHRASE` (M03A), as
secrets. `AWS_ACCOUNT_ID` is a repository variable, so `cdk-diff` on a
pull request from this repository can read it.

The list with values and timing is in
[`owner-checklist.md`](owner-checklist.md), under O04.

## 4. Lambda functions

| Function | Folder | Handler | Timeout | Memory | Holds |
| --- | --- | --- | --- | --- | --- |
| `AdminApiFn` | `backend/lambda/engine` | `api_handler.lambda_handler` | 29 s | 512 MB | Table read/write, data bucket read, invoke `EngineFn` async |
| `EngineFn` | `backend/lambda/engine` | `jobs_handler.lambda_handler` | 900 s | 2048 MB | Table, buckets, both secrets, Bedrock retrieve and ingest, SES send |
| `PreTokenGenerationFn` | `backend/lambda/pre_token_generation` | `handler.lambda_handler` | 10 s | 256 MB | Nothing |
| `PublicApiKeyAuthorizerFn` | `backend/lambda/public_api_authorizer` | `handler.lambda_handler` | 5 s | 256 MB | Get and update on `APIKEY#*` rows only (M03A) |

Environment variables (both engine functions unless noted):

| Variable | Value |
| --- | --- |
| `RECORDS_TABLE_NAME`, `AUDIT_LOG_TABLE_NAME` | Table names |
| `DATA_BUCKET_NAME`, `KB_BUCKET_NAME` | Bucket names |
| `ENGINE_FUNCTION_NAME` | `AdminApiFn` only. Target for async job starts |
| `INGEST_ENABLED`, `COMMITTEE_ENABLED`, `TRADING_ENABLED`, `LEVERAGE_ENABLED`, `BRIEF_EMAIL_ENABLED` | Kill switch parameters |
| `BROKER_MODE` | `paper` |
| `PUBLIC_API_WRITES_ENABLED` | `AdminApiFn` only. From `PublicApiWritesEnabled` |
| `ALPACA_SECRET_ID`, `OPENROUTER_SECRET_ID` | `EngineFn` only. Secret names |
| `COMMITTEE_ANALYST_MODEL`, `COMMITTEE_CHAIR_MODEL` | `EngineFn` only |
| `KNOWLEDGE_BASE_ID`, `KB_DATA_SOURCE_IDS` | From M07 |
| `KB_MAX_RAW_BYTES`, `KB_MAX_RETRIEVALS_PER_MONTH` | Caps |
| `MAIL_SENDING_DOMAIN`, `BRIEF_FROM_LOCAL_PART`, `BRIEF_RECIPIENT_EMAIL` | `EngineFn` only |
| `SEC_CONTACT_EMAIL` | `EngineFn` only |
| `ADMIN_WEB_ORIGIN` | `https://admin.<domain>` for links in the email |

## 5. DynamoDB records table

Keys: `pk` (string), `sk` (string). Index `gsi1` with `gsi1pk`,
`gsi1sk`. TTL attribute `expiresAt` (epoch seconds). Pay per request,
point-in-time recovery on, encrypted with the shared key, `RETAIN`.

| Record | `pk` | `sk` | `gsi1pk` / `gsi1sk` | Milestone |
| --- | --- | --- | --- | --- |
| Runtime settings | `SETTINGS#global` | `META` | | M03 |
| Owner task | `OWNER_TASK#<id>` | `META` | | M03 |
| Job run | `JOB#<job>` | `RUN#<startIso>` | `JOBRUNS` / `<startIso>` | M03 |
| API key | `APIKEY#<scrypt digest>` | `META` | `APIKEYS` / `<createdAt>#<keyId>` | M03A |
| Job cursor | `JOB#<job>` | `STATE` | `JOBSTATE` / `<job>` | M04 |
| Universe | `UNIVERSE#<date>` | `META` | `UNIVERSE` / `<date>` | M04 |
| Screen run | `SCREEN#<date>` | `META` | `SCREENS` / `<date>` | M06 |
| Screen row | `SCREEN#<date>` | `RANK#<0001>#<symbol>` | | M06 |
| Backtest run | `BACKTEST#<runId>` | `META` | `BACKTESTS` / `<startIso>` | M06 |
| KB state | `KB#state` | `META` | | M07 |
| KB evaluation | `KB#eval` | `RUN#<startIso>` | | M07 |
| Usage day | `USAGE#<date>` | `LLM` or `KB` | | M07, M08 |
| Usage month | `USAGE#<yyyy-mm>` | `LLM` or `KB` | | M07, M08 |
| Committee run | `COMMITTEE#<runId>` | `META` | `COMMITTEE_RUNS` / `<startIso>` | M08 |
| Committee case | `COMMITTEE#<runId>` | `CASE#<symbol>` | | M08 |
| Thesis version | `THESIS#<symbol>` | `V#<iso>` | `THESIS_ACTIVE` / `<symbol>` when active | M08 |
| Methodology proposal | `PROPOSAL#<id>` | `META` | `PROPOSALS` / `<iso>` | M08 |
| Target portfolio | `PORTFOLIO#paper` | `TARGET#<date>` | | M09 |
| Position | `POSITION#paper` | `<symbol>` | | M09 |
| Ledger entry | `LEDGER#paper` | `TXN#<iso>#<seq>` | | M09 |
| Daily snapshot | `LEDGER#paper` | `SNAP#<date>` | | M09 |
| Order | `ORDER#<orderId>` | `META` | `ORDERS#<status>` / `<createdIso>` | M09 |
| Hold | `HOLD#<holdId>` | `META` | `HOLDS#<status>` / `<executeAtIso>` | M10 |
| Brief | `BRIEF#<date>` | `DAILY` or `REBALANCE` | `BRIEFS` / `<date>#<kind>` | M10 |
| Breaker | `BREAKER#<name>` | `STATE` | | M11 |
| Alert sent | `ALERT#<date>` | `<cause>` | | M11 |
| Gate check | `GATE#paper` | `CHECK#<date>` | | M11 |
| Drill record | `GATE#paper` | `DRILL#<date>` | | M11 |

`paper` in a key is the account id. Real money will use `live`, so the
two never mix. Job runs and usage rows expire after 400 days through
`expiresAt`. Ledger, orders, theses and snapshots never expire.

Audit table: `pk = USER#<sub>`, `sk = <epochMillis>#<action>`,
attributes `target`, `requestId`. Written on every state-changing API
call. A dashboard write keeps the Cognito `sub`, so older rows and new
rows share one partition key. A write made with an API key uses
`pk = USER#apikey:<keyId>`.

## 6. S3 data bucket layout

All objects are gzip JSON lines (`.jsonl.gz`) unless stated. One JSON
object per line.

| Prefix | Content |
| --- | --- |
| `reference/assets/date=<date>/assets.jsonl.gz` | Alpaca asset list |
| `reference/sec/company_tickers_exchange.json.gz` | SEC ticker to CIK map |
| `universe/date=<date>/members.jsonl.gz` | Universe members with sector and liquidity |
| `universe/date=<date>/build.json` | In-progress universe build, plain JSON rather than jsonl.gz: the company list, the cursor, and rows already prepared. A short `written` marker replaces that list once the members file is saved, and the object is removed when the weekly job finishes the coverage report |
| `prices/raw/date=<date>/bars.jsonl.gz` | Unadjusted daily bars, all symbols, one file per day |
| `prices/adj/part=<000>/bars.jsonl.gz` | Split- and dividend-adjusted history (total return), 100 symbols per part, rewritten weekly |
| `prices/split/part=<000>/bars.jsonl.gz` | Split-adjusted history (price only), same parts |
| `prices/monthly/month=<yyyy-mm>/stats.jsonl.gz` | Month-end close and median dollar volume per symbol, for the backtest |
| `reference/calendar/year=<yyyy>.json` | Trading sessions |
| `corporate-actions/date=<date>/actions.jsonl.gz` | Dividends and splits |
| `fundamentals/raw/cik=<cik>/companyfacts.json.gz` | SEC payload, trimmed to the concepts in use |
| `fundamentals/pit/cik=<cik>/facts.jsonl.gz` | Point-in-time rows |
| `filings/date=<date>/index.jsonl.gz` | New 10-K, 10-Q, 8-K filings of the day |
| `news/symbol=<symbol>/date=<date>.jsonl.gz` | News items |
| `screens/date=<date>/scores.jsonl.gz` | Full factor table for every universe member |
| `backtests/<runId>/...` | Backtest inputs, monthly holdings, equity curve |
| `committee/<runId>/doctrine.json` | Knowledge base passages used by the run |
| `committee/<runId>/<symbol>/<role>.json` | Full prompt and response for audit |
| `briefs/date=<date>/<kind>.json` | The brief (`daily` or `rebalance`) |

Knowledge base bucket:

| Prefix | Content | Written by |
| --- | --- | --- |
| `theory/` | PDFs and optional `<file>.metadata.json` | Owner |
| `formula-notes/` | Markdown notes with exact formulas | Owner or developer after owner review |
| `journal/` | Monthly reviews and thesis post-mortems as Markdown | `EngineFn` |
| `eval/questions.json` | The 20 retrieval test questions. Not a data source | Owner |

## 7. Contracts

| File | Content | Zone |
| --- | --- | --- |
| `contracts/roadmap.json` | Milestones and steps with status | green |
| `contracts/admin-domains.json` | Storage key prefix and default hostnames | red |
| `contracts/jobs.json` | Job names, schedules, timeouts, manual-run allow-list, `keyRun` | red |
| `contracts/public-api-scopes.json` | API key scopes and tiers | red |
| `contracts/methodology.json` | Universe, factors, composite, screen, backtest, portfolio, leverage, exits, execution, tax | red |
| `contracts/fundamentals.json` | Our field names mapped to XBRL tags | red |
| `contracts/sic-sectors.json` | SIC code ranges mapped to sectors | red |
| `contracts/committee.json` | Roles, doctrine questions, output limits | red |
| `contracts/budgets.json` | Model and KB caps | red |
| `contracts/gate.json` | Go-live criteria | red |

Generated by `scripts/sync-contracts.py`:
`backend/lambda/engine/contracts/` (copies),
`backend/lambda/engine/contract_constants.py`,
`apps/admin_web/src/lib/contracts/generated.ts`,
`backend/infrastructure/lib/shared-contracts.ts`.

## 8. HTTP API routes

**Dashboard routes** use the Cognito JWT authorizer, and every handler
also calls `_require_admin`. `/health` has no authorizer.

**Key routes**: each dashboard route with a scope in the "Key scope"
column is also served at `/public/<same path>` with the `x-api-key`
header. The HTTP API exposes that mirror as one proxy
(`/public/{proxy+}`), so a later milestone does not add an
infrastructure route when it fills in a row below. Key callers use
`https://api.<domain>`. The dashboard uses the `AdminApiBaseUrl` stack
output. Both reach the same API. "owner only" means no key can reach
it. A write needs the scope `operate`, `allowWrite` on the key, and
`PublicApiWritesEnabled`. A settings write may only set switches to
false. Turning a switch on, resetting a breaker, ticking an owner
task, listing keys, and every real-money approval stay owner only.
The key list never includes the digest.

| Method and path | Purpose | Milestone | Key scope |
| --- | --- | --- | --- |
| `GET /health` | Liveness, no auth | M02 | not mirrored |
| `GET /me` | Claims of the caller | M02 | owner only |
| `GET /system/status` | Kill switches, last run per job, breakers, versions | M03 | `system` |
| `GET /settings` | Runtime settings | M03 | `system` |
| `PUT /settings` | Change runtime switches | M03 | `operate`, and only to turn switches off |
| `GET /owner-tasks` | Owner checklist | M03 | `system` |
| `PUT /owner-tasks/{taskId}` | Tick an owner task | M03 | owner only |
| `GET /jobs/runs` | Recent job runs | M03 | `system` |
| `GET /public` | The routes the calling key may use | M03A | any key |
| `GET /api-keys` | Key list without digests | M03A | owner only |
| `POST /jobs/{jobName}/run` | Start an allowed job. A `backtest` body may set `portfolioSize` inside the register bounds. The response echoes it. An unfinished run of another size is 409. Any other body is 400. Returns 202 `{accepted: true}` | M04 | `operate`, jobs with `keyRun` only |
| `GET /universe/latest` | Universe summary | M04 | `research` |
| `GET /methodology` | The register, its hash, and provisional, cited, and owner-accepted counts | M05 | `research` |
| `GET /screens/latest`, `GET /screens/{date}` | Shortlist and scores | M06 | `research` |
| `GET /backtests`, `GET /backtests/{runId}` | Backtest results | M06 | `research` |
| `GET /kb/status`, `GET /kb/eval/latest` | Knowledge base | M07 | `research` |
| `POST /kb/sync` | Start a knowledge base sync. The body matches `kb_sync_check`: empty, `{"confirmDeletion": true}`, or `{"stop": true}`. A key cannot confirm a deletion, stop a sync, or start the first sync | M07 | `operate` |
| `GET /costs` | Month-to-date spend against budget | M08 | `system` |
| `GET /committee/runs`, `GET /committee/runs/{runId}` | Committee output | M08 | `research` |
| `GET /theses`, `GET /theses/{symbol}` | Thesis journal | M08 | `research` |
| `GET /proposals` | Methodology proposals | M08 | `research` |
| `GET /portfolio/summary`, `GET /portfolio/positions`, `GET /portfolio/history` | Portfolio | M09 | `portfolio` |
| `GET /ledger` | Ledger entries, paged | M09 | `portfolio` |
| `GET /holds` | Holds | M10 | `portfolio` |
| `POST /holds/{holdId}/veto` | Veto a hold | M10 | `operate` |
| `GET /briefs`, `GET /briefs/{date}` | Daily briefs | M10 | `portfolio` |
| `GET /breakers` | Breakers | M11 | `system` |
| `POST /breakers/{name}/reset` | Reset a breaker | M11 | owner only |
| `GET /gate` | Go-live gate report | M11 | `system` |

## 9. Jobs and schedules

`EngineFn` receives `{"job": "<name>", ...}`. Schedules are EventBridge
Scheduler schedules (not `events.Rule`) with an IAM-role target.

| Job | Schedule name | Cron | Time zone | Kill switch |
| --- | --- | --- | --- | --- |
| `kb_sync_check` | `findingalpha-kb-sync-check` | `30 5 * * ? *` | Asia/Hong_Kong | none |
| `ingest_daily` | `findingalpha-ingest-daily` | `0 12 ? * TUE-SAT *` | Asia/Hong_Kong | `IngestEnabled` |
| `reconcile` | `findingalpha-reconcile` | `30 12 ? * TUE-SAT *` | Asia/Hong_Kong | `TradingEnabled` |
| `daily_check` | `findingalpha-daily-check` | `40 12 ? * TUE-SAT *` | Asia/Hong_Kong | `TradingEnabled` |
| `brief_compile` | `findingalpha-brief-compile` | `15 13 ? * TUE-SAT *` | Asia/Hong_Kong | none |
| `brief_send` | `findingalpha-brief-send` | `30 13 ? * TUE-SAT *` | Asia/Hong_Kong | `BriefEmailEnabled` |
| `execute_holds` | `findingalpha-execute-holds` | `45 9 ? * MON-FRI *` | America/New_York | `TradingEnabled` |
| `post_trade` | `findingalpha-post-trade` | `30 16 ? * MON-FRI *` | America/New_York | `TradingEnabled` |
| `weekly_refresh` | `findingalpha-weekly-refresh` | `0 8 ? * SUN *` | Asia/Hong_Kong | `IngestEnabled` |
| `monthly_rebalance` | `findingalpha-monthly-rebalance` | `0 8 ? * 7#1 *` | Asia/Hong_Kong | `CommitteeEnabled` |
| `monthly_review` | `findingalpha-monthly-review` | `0 10 ? * 1#1 *` | Asia/Hong_Kong | `CommitteeEnabled` |
| `tick` | `findingalpha-tick` | `rate(15 minutes)` | | none |

`7#1` is the first Saturday and `1#1` the first Sunday in EventBridge
cron syntax. Check both in the Scheduler console after the first deploy.

A job that is switched off still writes a job run with status
`skipped_disabled`, so the dashboard shows that it was asked to run.
A run that stops with time left, or pauses, is `partial` and carries
the cursor, for example `9 of 131, continues on the next tick`. A run
that returns `missing_inputs` is `failed`. A clean finish is
`succeeded`. `partial` is neither a success nor a failure.

Jobs without a schedule, started from the dashboard through
`POST /jobs/{jobName}/run` when `contracts/jobs.json` allows it:
An API key can start a job only when the job has `keyRun: true`.
Every job except `kb_eval` has that flag, including the broker jobs
and the drills. A key cannot start the evaluation. The owner runs it,
and only after a sync has stored a manifest. A key that asks to start a backfill
whose saved state is already `done` is refused, because that starts
the download again from the first month. The dashboard can still
start it. The system status reports `keyRun` and the saved
`progress` for each job. A `backtest` request may send
`{"portfolioSize": N}`. `N` has to be an integer from
`portfolioSizeMin` to `portfolioSizeMax` in the register. An empty body
uses the register size and the audit row records that size. A body that
is not a JSON object is refused, as is a body on any job other than
`backtest` and `kb_sync_check`. `kb_sync_check` accepts an empty body,
`{"confirmDeletion": true}`, or `{"stop": true}`, and nothing else.
The daily schedule does not start the first sync; Run now does. A
deletion above 15% is checked per data source, and the sync waits
until the owner confirms it from the dashboard. An API key cannot
confirm a deletion, stop a sync, or start the first sync. A key can
start a later sync. A problem file is recorded and skipped. A prefix
with no files, and none in the last sync, is not started. A size
that would replace an unfinished run is 409, and the saved run stays.
The 202 body echoes `portfolioSize` when one was sent. A tick that
cannot resume a job is `failed` and names that job.

| Job | Purpose | Milestone |
| --- | --- | --- |
| `backfill_prices` | Raw bars from 2016-01-01 through the saved end date | M04 |
| `backfill_fundamentals` | Company facts for every candidate CIK | M04 |
| `screen` | Score the universe for one date. Checks `IngestEnabled`. Also called by `monthly_rebalance` | M06 |
| `backfill_monthly_stats` | Month-end statistics for the backtest. Checks `IngestEnabled` | M06 |
| `backtest` | One backtest run. Checks `IngestEnabled` | M06 |
| `kb_sync_check` | Sync the knowledge base. The schedule waits until the first Run now | M07 |
| `kb_eval` | Retrieval evaluation | M07 |
| `committee_dry_run` | Three symbols, no thesis written | M08 |
| `committee_eval` | Five invented companies with known answers | M08 |
| `portfolio_propose` | Target portfolio and proposed orders | M09 |
| `broker_setup` | Account configuration and opening balance | M09 |
| `broker_smoke` | One-share round trip on paper | M09 |
| `leverage_overlay` | Replay of the leverage rule on the backtest | M09 |
| `breaker_drill` | Trips `data_stale` for the drill | M11 |
| `record_drill` | Stores the drill result for the gate | M11 |

## 10. Engine modules (target)

Flat files in `backend/lambda/engine/`, each at most 500 lines, each
with a `test_<name>.py` beside it.

| Area | Modules |
| --- | --- |
| Entry | `api_handler`, `jobs_handler`, `router`, `public_api`, `http_common`, `runtime`, `config`, `timeutil` |
| Storage | `store`, `s3io`, `settings`, `owner_tasks`, `system_status`, `kill_switch`, `job_runs`, `chunked`, `audit`, `secrets_read`, `http_client` |
| Data | `alpaca_data`, `sec_edgar`, `universe`, `ingest_prices`, `ingest_fundamentals`, `fundamentals_pit`, `ingest_news`, `market_calendar` |
| Method | `methodology`, `snapshot`, `factors_quality`, `factors_value`, `factors_trend`, `composite`, `screen`, `backtest`, `backtest_metrics` |
| Knowledge | `kb_client`, `kb_sync`, `kb_eval` |
| Models | `openrouter_client`, `llm_budget`, `fact_sheet`, `doctrine`, `committee`, `committee_prompts`, `committee_schema`, `thesis_store`, `monthly_review` |
| Money | `portfolio`, `leverage`, `limits`, `orders`, `broker`, `broker_alpaca`, `ledger`, `tax`, `benchmark`, `reconcile` |
| Daily | `daily_check`, `holds`, `brief`, `brief_email`, `costs` |
| Safety | `breakers`, `gate` |

## 11. External services

| Service | Base URL | Auth | Limit to respect |
| --- | --- | --- | --- |
| Alpaca paper trading | `https://paper-api.alpaca.markets` | Key id and secret headers | 200 requests a minute |
| Alpaca market data | `https://data.alpaca.markets` | Same keys | 200 requests a minute on the free plan |
| SEC EDGAR | `https://data.sec.gov`, `https://www.sec.gov` | None. `User-Agent` with contact email is required | 10 requests a second. Use 5 |
| OpenRouter | `https://openrouter.ai/api/v1` | Bearer key | Budget in `contracts/budgets.json` |
| Bedrock Managed KB | AWS SDK `bedrock-agent`, `bedrock-agent-runtime` | IAM | 5,000 retrievals a month (own cap) |
| SES | AWS SDK `sesv2` | IAM | One recipient |
| Cloudflare DNS | `https://api.cloudflare.com/client/v4` | Token in the developer's environment, never in git | This project's zone only. Not used by the running system |

Confirm each limit and price when the milestone starts. They change.
