# Plan: M03 admin dashboard

**Status**: Done. The live Google sign-in check is closed.
**Zone**: yellow (`apps/admin_web/src/**`, new engine routes). The two
route entries in `backend/infrastructure/lib/api-routes.ts` are red:
ask before that edit.

## Goal

A private dashboard at `https://admin.<domain>` where the owner signs in
with Cognito, exactly as on `admin.lx-software.com`, and sees how far
the build is and whether the system is healthy. This milestone ships
the shell, sign-in, the **Roadmap** page and the **System** page. Later
milestones each add their own page (table at the end).

## Non-goals

- No public pages. Everything except the login screen needs the `admin`
  group.
- No new sign-in method. Google federation with the allow-list, plus
  the one bootstrap user with TOTP.
- No Tailwind, no chart library, no state library beyond TanStack Query.
- No trading controls yet. Veto and breaker reset arrive with M10 and
  M11.

## Sign-in strategy (same as `admin.lx-software.com`)

1. The login screen offers **Sign in with Google** and **Sign in with
   email** (the bootstrap user).
2. The SPA starts an authorization-code flow with PKCE and a random
   `state` against the Cognito Hosted UI.
3. Cognito calls the gate Lambda. An account that is not on
   `AdminFederatedEmailAllowlist` is refused and gets no token. The
   login screen then shows "This account is not authorized."
4. On success the SPA exchanges the code at `/oauth2/token` and keeps
   the ID, access and refresh tokens in `sessionStorage`.
5. Every API call sends the **ID token** as `Authorization: Bearer`.
   API Gateway checks it. The handler checks the `admin` group again.
6. Sign-out revokes the refresh token, clears storage and goes through
   the Cognito `/logout` endpoint.

The allow-list is the complete list of people who can see the
dashboard. For this project it holds one address.

## Files

```
apps/admin_web/package.json  package-lock.json  index.html
apps/admin_web/vite.config.ts  eslint.config.js  playwright.config.ts
apps/admin_web/tsconfig.json  tsconfig.app.json  tsconfig.node.json
apps/admin_web/.env.example  .env.mock
apps/admin_web/public/favicon.svg
apps/admin_web/src/main.tsx  App.tsx  index.css
apps/admin_web/src/components/AuthProvider.tsx  RequireAuth.tsx
apps/admin_web/src/components/AuthenticatedShell.tsx  LazyPage.tsx
apps/admin_web/src/components/RouteErrorBoundary.tsx
apps/admin_web/src/components/ui/  (AdminKpi, AdminDataTable, ConfirmDialog,
                                    DateTimeDisplay, AdminTabList, index.ts)
apps/admin_web/src/components/roadmap/  (MilestoneCard, StepList, OwnerTaskList,
                                         PhaseStrip)
apps/admin_web/src/components/system/   (KillSwitchTable, JobTable)
apps/admin_web/src/hooks/useRunOncePerPageLoad.ts  useOwnerTasks.ts
apps/admin_web/src/hooks/useSystemStatus.ts  useSettings.ts
apps/admin_web/src/lib/auth.ts  jwt.ts  pkce.ts  config.ts
apps/admin_web/src/lib/apiAdminClient.ts  adminNav.ts  queryKeys.ts
apps/admin_web/src/lib/roadmapModel.ts
apps/admin_web/src/lib/contracts/generated.ts          (generated)
apps/admin_web/src/lib/mock/isAdminMockEnabled.ts  mockAdminApi.ts  fixtures.ts
apps/admin_web/src/lib/mock/routes/types.ts  context.ts  index.ts  system.ts
apps/admin_web/src/pages/LoginPage.tsx  AuthCallbackPage.tsx
apps/admin_web/src/pages/RoadmapPage.tsx  SystemPage.tsx
apps/admin_web/e2e/smoke.spec.ts
backend/lambda/engine/settings.py  owner_tasks.py  system_status.py  (+ tests)
backend/lambda/engine/api_handler.py                   (new routes)
backend/infrastructure/lib/api-routes.ts               (red: new routes)
```

## Invariants this change preserves

- A session without the `admin` group in the ID token is cleared and
  sent to the login screen.
- The API never trusts the SPA. Every handler calls `_require_admin`.
- `VITE_ADMIN_MOCK=1` is never set in a production build.
- The Content-Security-Policy stays `script-src 'self'`. No inline
  scripts, no remote fonts, no `dangerouslySetInnerHTML`.
- Bootstrap 5 classes and the shared `ui` components. Functional
  components, named exports, TypeScript.
- Every state-changing call writes an audit row.
- No real email or name in fixtures. Use `mock.admin@example.com`.

## Steps

### M03-T01 Scaffold the app

1. Copy from `lx-software` `apps/admin_web`: `package.json`,
   `index.html`, `vite.config.ts`, `eslint.config.js`,
   `playwright.config.ts`, the three `tsconfig` files, `.env.example`,
   `.env.mock`.
2. `package.json`: name `findingalpha-admin-web`. Keep every dependency
   and its version. Change `test:backend` to:
   ```
   cd ../../backend/lambda/engine && python3 -m unittest discover -p 'test_*.py' -v && cd ../pre_token_generation && python3 -m unittest discover -p 'test_*.py' -v
   ```
3. `index.html`: title `Finding Alpha | Admin`, description
   `findingalpha admin console.`, one SVG favicon.
4. `npm install`, commit `package-lock.json`.
5. Remove the M01 guards from `lint-admin-web`, `build-admin-web` and
   `e2e-admin-web`.

### M03-T02 Auth and API client

Copy these files. Change only what is listed.

| File | Change |
| --- | --- |
| `src/lib/pkce.ts`, `src/lib/jwt.ts` | None |
| `src/lib/config.ts` | None |
| `src/lib/auth.ts` | Storage keys: replace the prefix `lx_admin` with the generated constant `storageKeyPrefix` (`fa_admin`) |
| `src/components/AuthProvider.tsx` | Same prefix change for the PKCE verifier and state keys |
| `src/components/RequireAuth.tsx`, `LazyPage.tsx`, `RouteErrorBoundary.tsx` | None |
| `src/pages/LoginPage.tsx` | Product name. Keep both buttons and the denied-message flash |
| `src/pages/AuthCallbackPage.tsx` | Same prefix change |
| `src/hooks/useRunOncePerPageLoad.ts` | None |
| `src/lib/apiAdminClient.ts` | Keep `AdminApiError`, `getAdminApiErrorMessage`, `joinUrl`, `adminFetch`, `adminFetchJson`. Remove the asset helpers |
| `src/lib/mock/isAdminMockEnabled.ts`, `mockAdminApi.ts`, `routes/types.ts`, `routes/context.ts` | Keep the mock ID token builder and `installAdminMockSession` |
| `src/main.tsx` | None |

Copy the matching test files (`auth.test.ts`, `jwt.test.ts`,
`config.test.ts`, `apiAdminClient.test.ts`) and make them pass before
writing any page.

### M03-T03 Shell and navigation

1. Copy `AuthenticatedShell.tsx` and the shell part of `index.css`
   (classes starting `admin-`).
2. `src/lib/adminNav.ts`: same types. In this milestone:
   ```ts
   export const ADMIN_NAV_GROUPS: readonly (readonly AdminNavItem[])[] = [
     [
       { to: "/", label: "Roadmap", icon: "bi-signpost-split", end: true },
       { to: "/system", label: "System", icon: "bi-activity" },
     ],
   ];
   ```
   A page gets its nav entry in the milestone that builds it. No dead
   links.
3. `App.tsx`: same structure as the sibling. Routes:
   `/auth/callback`, then inside `RequireAuth` and `AuthenticatedShell`:
   index `RoadmapPage`, `system` `SystemPage`. Unknown paths redirect to
   `/`.

### M03-T04 Roadmap data

1. Extend `scripts/sync-contracts.py` so `generated.ts` exports
   `ROADMAP` (the whole of `contracts/roadmap.json`), `ADMIN_DOMAINS`
   and `JOBS`.
2. `src/lib/roadmapModel.ts`, pure functions with unit tests:
   - `milestoneProgress(m)` returns `{ done, total, percent }`.
   - `overallProgress(roadmap)` returns the same over all steps.
   - `currentMilestone(roadmap)` returns the first milestone that is
     `in_progress`, else the first `not_started`.
   - `blockingOwnerTasks(m, roadmap, doneIds)` returns the open owner
     tasks whose `blocks` contains the milestone id.
   - `planUrl(m)` returns
     `https://github.com/lx-software-ltd/findingalpha/blob/main/<plan>`.
3. Tests: empty milestone, all done, a blocked milestone, an unknown
   status (falls back to `todo`).

### M03-T05 Engine routes for the dashboard

Write tests first. All handlers call `_require_admin` and return 403
otherwise.

| Route | Module | Behaviour |
| --- | --- | --- |
| `GET /owner-tasks` | `owner_tasks.py` | `{ "done": { "<id>": { "at": "<iso>" } } }` from `OWNER_TASK#<id>` rows |
| `PUT /owner-tasks/{taskId}` | `owner_tasks.py` | Body `{ "done": true }`. Id must match `^O[0-9]{2}$`. Writes or deletes the row. Audit action `owner_task_set` |
| `GET /settings` | `settings.py` | The runtime settings row, defaults filled in |
| `PUT /settings` | `settings.py` | Body may contain only the five switch keys, each a boolean. Unknown key: 400. Audit action `settings_put` with the changed keys |
| `GET /jobs/runs` | `system_status.py` | Query `gsi1pk = JOBRUNS`, newest first, `limit` 1 to 100, default 50 |
| `GET /system/status` | `system_status.py` | See below |

`GET /system/status` response:

```json
{
  "switches": [
    { "name": "ingestEnabled", "parameter": false, "setting": false, "effective": false }
  ],
  "brokerMode": "paper",
  "jobs": [
    { "job": "tick", "schedule": "rate(15 minutes)", "lastRun": { "status": "succeeded", "startedAt": "...", "durationMs": 120, "message": "" } }
  ]
}
```

`jobs` lists every job in `contracts/jobs.json`, with `lastRun: null`
when it never ran. Read the latest run with one query per job
(`pk = JOB#<job>`, `sk` begins with `RUN#`, descending, limit 1).

Runtime setting names are camel case (`ingestEnabled`,
`committeeEnabled`, `tradingEnabled`, `leverageEnabled`,
`briefEmailEnabled`). `kill_switch.is_enabled` from M02 reads them.

Add the six routes to `ROUTES` in `api-routes.ts` with `auth: "jwt"`
(red: ask first) and to the route table in `api_handler.py`.

### M03-T06 Roadmap page

Layout, top to bottom:

1. **Phase strip.** Four labelled segments: Build, Paper trading, Gate,
   Real money. The active one is highlighted. Until M11 the active
   segment is always Build. From M11 it comes from `GET /gate`.
2. **Four KPI tiles** (`AdminKpi`): steps done out of total with
   percent; milestones done out of total; current milestone id and
   title; open owner tasks.
3. **Owner tasks.** A list with a checkbox per task, the title, and
   badges for the milestones it blocks. Ticking calls
   `PUT /owner-tasks/{id}` and updates optimistically, rolling back on
   error. Open tasks that block the current milestone are listed
   first with a warning colour.
4. **Milestones.** One card per milestone, in order: id, title, status
   badge (`not_started` grey, `in_progress` blue, `blocked` amber,
   `done` green), zone badge, a Bootstrap progress bar, "Blocked by
   O04, O06" when owner tasks are open, a link to the plan file, links
   to pull requests. A disclosure opens the step list: status icon, id,
   title.

Roadmap content comes from the generated constant, so it changes only
when a pull request changes `contracts/roadmap.json` and the SPA is
redeployed. Owner task ticks are live.

Tests (Vitest + Testing Library): renders counts from a fixture;
ticking a task calls the API and reverts on a 500; a blocked milestone
shows its owner tasks.

### M03-T07 System page

1. **Switches.** A table: name, parameter, setting (a switch control),
   effective. The parameter column is read-only with the hint "Change
   in the parameter file and redeploy". Turning a setting on or off
   asks for confirmation (`ConfirmDialog`) and calls `PUT /settings`.
   When the parameter is off the row says the setting has no effect
   until the parameter is on.
2. **Broker mode.** A badge: `paper`.
3. **Jobs.** A table (`AdminDataTable`): job, schedule, last status
   badge, started (Hong Kong time through `DateTimeDisplay`), duration,
   message. A job that last failed is shown first.
4. **Recent runs.** The last 50 runs.

The page refetches every 60 seconds while visible.

### M03-T08 Mock mode and smoke test

1. `src/lib/mock/fixtures.ts`: owner tasks, settings, a status payload
   with one succeeded, one failed and one never-run job.
2. `src/lib/mock/routes/system.ts`: handlers for the six routes with
   in-memory state. Register in `routes/index.ts`.
3. `src/lib/mock/mockAdminApi.test.ts`: each route returns the fixture
   and `PUT` changes state.
4. `e2e/smoke.spec.ts`, modelled on `mobile-smoke.spec.ts`: on phone,
   tablet and desktop, the Roadmap page renders without horizontal
   scroll, the nav opens, the System page shows the three tables.
5. `npm run dev:mock` and click through both pages by hand. Tick a
   task, flip a switch, confirm the UI updates.

### M03-T09 Deploy and sign-in test

Needs M02 deployed and owner tasks O08 and O09.

1. Merge. **Deploy Backend** then **Deploy Admin Web** run.
2. Follow the smoke test in `docs/deployment/admin-website.md`:
   - The login screen appears at `https://admin.<domain>`.
   - Google sign-in with the allow-listed account lands on Roadmap.
   - `sessionStorage` holds the tokens.
   - Sign out returns to the login screen.
   - The owner tries a Google account that is **not** on the list:
     back on the login screen with "This account is not authorized.",
     no tokens, no new user in the Cognito console.
   - The bootstrap user signs in with email, sets a password and TOTP.
3. On System, the `tick` job shows a recent successful run.

## Done when

- In `apps/admin_web`: `npm run lint`, `npm test`, `npm run build`,
  `npm run test:e2e` pass.
- Engine unit tests pass.
- The CSP in the browser console shows no violation on either page.
- T09 passes. Add screenshots of Roadmap and System (mock mode is
  fine) to the pull request.

## Rollback

Revert the pull request. The web deploy re-uploads the previous build.
The new DynamoDB rows are harmless and stay.

## Open questions

- None that block. The page list below is the plan for later
  milestones and can be reordered by the owner.

## Pages added by later milestones

Each later milestone adds the page, its nav entry, mock fixtures, a
unit test and a line in the smoke test. Group the nav as: Roadmap and
System; Portfolio, Holds, Briefs, Theses; Screen, Methodology,
Knowledge base, Costs, Gate.

| Milestone | Page | Path | Shows |
| --- | --- | --- | --- |
| M04 | Data (section on System) | `/system` | Universe size and date, last price date, fundamentals coverage, a "Run now" button per allowed job |
| M05 | Methodology | `/methodology` | Every factor and rule with formula text, value, citation, status (`provisional` or `cited`) |
| M06 | Screen | `/screen` | Latest shortlist with factor scores. Backtest results: equity curve against SPY gross and net, yearly table |
| M07 | Knowledge base | `/kb` | Documents, size against the 2 GB cap, last sync, retrievals this month against the cap, evaluation score, "Sync now" |
| M08 | Theses | `/theses` | Active theses: verdict, conviction, kill criteria, citations. Committee runs with each role's argument |
| M08 | Costs | `/costs` | Month to date against the budget lines of `00-overview.md` section 6 |
| M09 | Portfolio | `/portfolio` | Equity, cash, leverage, drawdown, positions, performance against both benchmarks, tax provision lines |
| M10 | Holds | `/holds` | Pending holds with countdown and a Veto button. History |
| M10 | Briefs | `/briefs` | The daily briefs, newest first |
| M11 | Gate | `/gate` | Each go-live criterion, its current value, pass or fail. Breakers with a Reset button |

Charts are a small hand-written SVG line chart component
(`components/ui/LineChart.tsx`, added in M06). Long text from the
models is rendered with `react-markdown`, never as raw HTML.
