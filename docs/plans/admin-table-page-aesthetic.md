# Plan: admin table and page aesthetic

**Status**: Done
**Zone**: yellow (`apps/admin_web/src/**`, `docs/plans/**`)

## Goal

Make the Roadmap, System, Methodology, and Screen pages use the same
page and table composition as `lx-software` admin: a page header, a KPI
strip, section titles, pill tabs, and record tables with the shared
header, density, sort control, and column priority.

## Non-goals

- No new routes, API fields, or contract edits.
- No finance-only widgets (money totals, row kebab menus, editor panels).

## Files

- `apps/admin_web/src/components/ui/AdminPageHeader.tsx`
- `apps/admin_web/src/components/ui/AdminRecordTable.tsx`
- `apps/admin_web/src/components/ui/AdminExpandableRow.tsx`
- `apps/admin_web/src/components/ui/AdminEditorSection.tsx`
- `apps/admin_web/src/components/ui/TableSortHeaderButton.tsx`
- `apps/admin_web/src/components/ui/AdminTabList.tsx`
- `apps/admin_web/src/lib/adminTabs.ts`
- `apps/admin_web/src/lib/recordGroup.ts`
- `apps/admin_web/src/pages/RoadmapPage.tsx`
- `apps/admin_web/src/pages/SystemPage.tsx`
- `apps/admin_web/src/pages/MethodologyPage.tsx`
- `apps/admin_web/src/pages/ScreenPage.tsx`
- Unit tests beside the new components, and the existing page tests

## Invariants this change preserves

- Bootstrap 5 only. No Tailwind.
- Roadmap still shows the phase strip, four KPIs, owner-task checkboxes,
  and one card per milestone with status, zone, progress, and steps.
- System still shows switches, broker mode, universe counts, jobs, recent
  runs, and API keys. Run, stop, and deletion still confirm first.
- Screen still sorts the shortlist, opens a name, and charts a backtest.
  Sorting an active column reverses direction. A phone uses a sort field
  because those columns are hidden. Missing composites sort last in either
  direction. Equal ranks and symbols break the tie by symbol, then rank.
- The shortlist symbol and the methodology factor name are buttons with
  `aria-expanded`. A pointer click on the rest of the row still opens it.
  The detail is not in the page while the row is closed.
- The backtest run select is rendered once. The previous curves stay up
  while the next run loads. A failed load shows an alert.
- Headings the smoke test looks for stay headings: Roadmap's "Owner tasks",
  "Methodology", "Screen", "Switches", "Jobs", and "Recent runs".
- A phone can still read rank, formula, period (including the period name
  on a benchmark row), key expiry, key scopes, key created and last used,
  job schedule, started, and duration, recent-run started and duration, and
  the switch redeploy hint. Hidden group scores and factor parameters open
  with the row.
- Broker mode shows `paper` until status has loaded.

## Done when

- `npm test` in `apps/admin_web` passes.
- `npm run lint` in `apps/admin_web` passes.
- `npm run dev:mock` and a click-through of the four pages, including the
  shortlist expand, a reversed sort, the backtest tab, and a roadmap checkbox.
- `npm run test:e2e` asserts the phone sort field, the rank line, a period
  CAGR, and a factor formula at 390px.

## Rollback

Revert the branch. No data or contract changes.

## Open questions

None.
