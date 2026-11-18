import { useMemo, useState } from "react";
import {
  AdminCell,
  AdminDataTable,
  AdminDataTableCellMeta,
  AdminDataTableEmptyRow,
  AdminEditorSection,
  AdminExpandableRow,
  AdminFilterBar,
  AdminFilterField,
  AdminKpi,
  AdminPageHeader,
  AdminRecordTable,
  AdminTabList,
  LineChart,
  TableSortHeaderButton,
  type AdminDataTableColumn,
} from "../components/ui";
import {
  useBacktest,
  useBacktests,
  useScreen,
  type PeriodMetrics,
  type ScreenRow,
  type SeriesMetrics,
} from "../hooks/useScreen";
import { adminTabButtonId } from "../lib/adminTabs";

const BIASES = [
  "Adjusted prices include every name that passed the price and dollar-volume floors in any month since February 2017 and still has a CIK. A delisted name with no current CIK has no prices and cannot be ranked. A name never stored in a universe file uses today's CIK and the SIC cached from SEC submissions; a missing SIC excludes it. A reused ticker with no universe row is left out. When monthly stats are missing, only today's members are priced and the weekly result says so.",
  "Sector and SIC code are the latest stored codes, not the codes at the time.",
  "Shares outstanding come from filings and can lag buybacks and issues by a quarter.",
  "When a filing has only LongTermDebt and DebtCurrent, total debt is the larger figure. Borrowings that sit in DebtCurrent and were never inside LongTermDebt are missed. Adding the two totals would count the current portion twice.",
  "Notes, convertibles, other long-term debt, commercial paper, and the lease-inclusive total are used only when the narrower tag is missing. Those fallbacks are not added together, and the lease-inclusive total includes leases.",
  "A name with no price on the trade date is counted and earns the cash return for that month. A month with no holdings earns the cash return.",
  "Trading at the close with a fixed cost ignores market impact.",
  "Dividend withholding is the gap between the adjusted and split price series.",
  "Ten years is mostly one bull market led by large technology companies.",
];

type Tab = "shortlist" | "backtest";
type SortKey = "rank" | "symbol" | "composite";

const SCREEN_TABS = [
  { id: "shortlist" as const, label: "Shortlist" },
  { id: "backtest" as const, label: "Backtest" },
];

export function ScreenPage() {
  const [tab, setTab] = useState<Tab>("shortlist");
  return (
    <div>
      <AdminPageHeader eyebrow="Finding Alpha" title="Screen" />
      <AdminTabList
        tabs={SCREEN_TABS}
        active={tab}
        onChange={setTab}
        label="Screen sections"
        idPrefix="screen"
        panelId="screen-panel"
      />
      <div
        id="screen-panel"
        role="tabpanel"
        aria-labelledby={adminTabButtonId("screen", tab)}
      >
        {tab === "shortlist" ? <Shortlist /> : <BacktestPanel />}
      </div>
    </div>
  );
}

function Shortlist() {
  const [date, setDate] = useState("");
  const [requested, setRequested] = useState("");
  const [sort, setSort] = useState<SortKey>("rank");
  const [open, setOpen] = useState("");
  const screen = useScreen(requested);
  const rows = useMemo(() => sortRows(screen.data?.rows ?? [], sort), [screen.data, sort]);
  const factorNames = Object.keys(rows[0]?.factors ?? {});
  const columns = useMemo(
    () => shortlistColumns(factorNames, sort, setSort),
    [factorNames, sort],
  );

  return (
    <div>
      {screen.isError ? <p>{screenMessage(screen.error)}</p> : null}
      <div className="admin-kpi-row">
        <AdminKpi label="Date" value={screen.data?.asOf ?? "—"} />
        <AdminKpi label="Universe" value={screen.data?.counts.universe ?? "—"} />
        <AdminKpi label="Passed" value={screen.data?.counts.passed ?? "—"} />
        <AdminKpi label="Shortlisted" value={screen.data?.counts.shortlisted ?? "—"} />
      </div>
      <p className="small text-muted">Register hash {screen.data?.registerHash ?? "—"}</p>
      <AdminRecordTable
        label="Shortlist"
        filters={
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setRequested(date);
            }}
          >
            <AdminFilterBar
              create={
                <button className="btn btn-outline-secondary btn-sm admin-create-btn" type="submit">
                  Load date
                </button>
              }
            >
              <AdminFilterField label="Date" htmlFor="screen-date">
                <input
                  id="screen-date"
                  className="form-control form-control-sm"
                  type="date"
                  value={date}
                  onChange={(event) => setDate(event.target.value)}
                />
              </AdminFilterField>
            </AdminFilterBar>
          </form>
        }
      >
        <AdminDataTable bare columns={columns}>
          {screen.isSuccess && rows.length === 0 ? (
            <AdminDataTableEmptyRow colSpan={columns.length} message="No names on this date." />
          ) : (
            rows.map((row) => (
              <Row
                key={row.symbol}
                row={row}
                factorNames={factorNames}
                colSpan={columns.length}
                open={open === row.symbol}
                onToggle={() => setOpen(open === row.symbol ? "" : row.symbol)}
              />
            ))
          )}
        </AdminDataTable>
      </AdminRecordTable>
    </div>
  );
}

function shortlistColumns(
  factorNames: readonly string[],
  sort: SortKey,
  setSort: (key: SortKey) => void,
): AdminDataTableColumn[] {
  const sortHeader = (key: SortKey, label: string): AdminDataTableColumn => ({
    key,
    header: (
      <TableSortHeaderButton
        label={label}
        isActive={sort === key}
        direction={sort === key ? (key === "composite" ? "desc" : "asc") : null}
        onClick={() => setSort(key)}
        align={key === "rank" || key === "composite" ? "end" : "start"}
      />
    ),
    thAriaSort: sort === key ? (key === "composite" ? "descending" : "ascending") : "none",
    className: key === "symbol" ? undefined : "text-end",
    priority: key === "symbol" ? "primary" : "secondary",
  });
  return [
    sortHeader("rank", "Rank"),
    sortHeader("symbol", "Symbol"),
    { key: "name", header: "Name", priority: "secondary" },
    { key: "sector", header: "Sector", priority: "tertiary" },
    sortHeader("composite", "Composite"),
    { key: "quality", header: "Quality", className: "text-end", priority: "secondary" },
    { key: "value", header: "Value", className: "text-end", priority: "tertiary" },
    { key: "trend", header: "Trend", className: "text-end", priority: "tertiary" },
    ...factorNames.map((name) => ({
      key: name,
      header: name,
      className: "text-end",
      priority: "tertiary" as const,
    })),
  ];
}

function Row({
  row,
  factorNames,
  colSpan,
  open,
  onToggle,
}: {
  readonly row: ScreenRow;
  readonly factorNames: readonly string[];
  readonly colSpan: number;
  readonly open: boolean;
  readonly onToggle: () => void;
}) {
  return (
    <AdminExpandableRow colSpan={colSpan} expanded={open} onToggle={onToggle} editor={<FactorDetail row={row} factorNames={factorNames} />}>
      <AdminCell column="rank" className="text-end">{row.rank}</AdminCell>
      <AdminCell column="symbol">
        <button
          type="button"
          className="btn btn-link admin-sort-header p-0 text-decoration-none fw-semibold"
          onClick={(event) => {
            event.stopPropagation();
            onToggle();
          }}
        >
          {row.symbol}
        </button>
        <AdminDataTableCellMeta>
          {row.name} · {figure(row.composite)}
        </AdminDataTableCellMeta>
      </AdminCell>
      <AdminCell column="name">{row.name}</AdminCell>
      <AdminCell column="sector">{row.sector}</AdminCell>
      <AdminCell column="composite" className="text-end">{figure(row.composite)}</AdminCell>
      <AdminCell column="quality" className="text-end">{figure(row.groups.quality)}</AdminCell>
      <AdminCell column="value" className="text-end">{figure(row.groups.value)}</AdminCell>
      <AdminCell column="trend" className="text-end">{figure(row.groups.trend)}</AdminCell>
      {factorNames.map((name) => (
        <AdminCell column={name} className="text-end" key={name}>{figure(row.factors[name])}</AdminCell>
      ))}
    </AdminExpandableRow>
  );
}

(Row as { recordGroup?: boolean }).recordGroup = true;

function FactorDetail({
  row,
  factorNames,
}: {
  readonly row: ScreenRow;
  readonly factorNames: readonly string[];
}) {
  return (
    <div className="row g-2">
      {factorNames.map((name) => (
        <div className="col-6 col-md-4" key={name}>
          {name}: {figure(row.factors[name])} (z {figure(row.z[name])})
        </div>
      ))}
    </div>
  );
}

function BacktestPanel() {
  const list = useBacktests();
  const runs = list.data?.runs ?? [];
  const [chosen, setChosen] = useState("");
  const runId = chosen || runs[0]?.runId || "";
  const detail = useBacktest(runId);
  const data = detail.data;
  const series = data
    ? [
        curve("Strategy", "#0f766e", data.labels, data.curves.strategy),
        curve("SPY net", "#5c6570", data.labels, data.curves.spyNet),
        curve("SPY gross", "#067647", data.labels, data.curves.spyGross),
      ]
    : [];
  const metricColumns: AdminDataTableColumn[] = [
    { key: "period", header: "Period" },
    { key: "series", header: "Series", priority: "secondary" },
    { key: "cagr", header: "CAGR", className: "text-end", priority: "secondary" },
    { key: "volatility", header: "Volatility", className: "text-end", priority: "tertiary" },
    { key: "sharpe", header: "Sharpe", className: "text-end", priority: "tertiary" },
    { key: "drawdown", header: "Max drawdown", className: "text-end", priority: "tertiary" },
  ];
  return (
    <div>
      {runs.length === 0 ? <p>No backtest is stored. The live runs wait until prices and fundamentals are in.</p> : null}
      {data ? (
        <>
          <div className="card shadow-sm mb-4">
            <div className="card-body">
              <h2 className="admin-card-title">Equity curves</h2>
              {runs.length > 0 ? (
                <div className="admin-filter-field mb-3">
                  <label className="form-label small mb-1" htmlFor="backtest-run">Run</label>
                  <select
                    id="backtest-run"
                    className="form-select form-select-sm"
                    value={runId}
                    onChange={(event) => setChosen(event.target.value)}
                  >
                    {runs.map((run) => (
                      <option key={run.runId} value={run.runId}>{run.runId} · {run.portfolioSize} names</option>
                    ))}
                  </select>
                </div>
              ) : null}
              <LineChart series={series} title="Backtest equity curves" formatY={(value) => value.toFixed(0)} />
            </div>
          </div>
          <h2 className="admin-card-title">Period metrics</h2>
          <AdminRecordTable label="Period metrics">
            <AdminDataTable bare columns={metricColumns} tableClassName="admin-table-keep-cols">
              <PeriodRows name="Full" metrics={data.metrics.full} />
              <PeriodRows name="2017–2021" metrics={data.metrics.early} />
              <PeriodRows name="2022 to today" metrics={data.metrics.holdout} />
            </AdminDataTable>
          </AdminRecordTable>
          <p>
            Hit rate {percent(data.metrics.hitRate)}. Average turnover {percent(data.metrics.averageTurnover)}.
            Yearly cost drag {percent(data.metrics.costDrag)}. Worst 12 months {percent(data.metrics.worstWindow?.return)}
            {" "}({data.metrics.worstWindow?.start ?? "—"} to {data.metrics.worstWindow?.end ?? "—"}).
            Longest stretch behind SPY net {data.metrics.longestBehind?.months ?? "—"} months
            {" "}({data.metrics.longestBehind?.start ?? "—"} to {data.metrics.longestBehind?.end ?? "—"}).
            Names carried at a last price {data.lastPriceCount ?? "—"}.
            Names without a trade price {data.unpricedCount ?? "—"}.
            Months missing a benchmark {data.missingBenchmarkCount ?? "—"}.
          </p>
          <h2 className="admin-card-title">Yearly returns</h2>
          <AdminRecordTable label="Yearly returns">
            <AdminDataTable
              bare
              tableClassName="admin-table-keep-cols"
              columns={[
                { key: "year", header: "Year" },
                { key: "strategy", header: "Strategy", className: "text-end" },
                { key: "benchmark", header: "SPY net", className: "text-end" },
              ]}
            >
              {(data.metrics.yearly ?? []).map((year) => (
                <tr key={year.year}>
                  <AdminCell column="year">{year.year}</AdminCell>
                  <AdminCell column="strategy" className="text-end">{percent(year.strategy)}</AdminCell>
                  <AdminCell column="benchmark" className="text-end">{percent(year.benchmark)}</AdminCell>
                </tr>
              ))}
            </AdminDataTable>
          </AdminRecordTable>
        </>
      ) : runs.length > 0 ? (
        <div className="admin-filter-field mb-3">
          <label className="form-label small mb-1" htmlFor="backtest-run">Run</label>
          <select
            id="backtest-run"
            className="form-select form-select-sm"
            value={runId}
            onChange={(event) => setChosen(event.target.value)}
          >
            {runs.map((run) => (
              <option key={run.runId} value={run.runId}>{run.runId} · {run.portfolioSize} names</option>
            ))}
          </select>
        </div>
      ) : null}
      <AdminEditorSection title="Known biases">
        <ul className="mb-0">{BIASES.map((note) => <li key={note}>{note}</li>)}</ul>
      </AdminEditorSection>
    </div>
  );
}

function PeriodRows({ name, metrics }: { readonly name: string; readonly metrics: PeriodMetrics | undefined }) {
  return (
    <>
      <MetricRow label={name} series="Strategy" metrics={metrics} />
      {metrics?.benchmarks?.spyNet ? <MetricRow label="" series="SPY net" metrics={metrics.benchmarks.spyNet} /> : null}
      {metrics?.benchmarks?.spyGross ? <MetricRow label="" series="SPY gross" metrics={metrics.benchmarks.spyGross} /> : null}
    </>
  );
}

function MetricRow({
  label,
  series,
  metrics,
}: {
  readonly label: string;
  readonly series: string;
  readonly metrics: SeriesMetrics | undefined;
}) {
  return (
    <tr>
      <AdminCell column="period">
        {label || series}
        {label ? <AdminDataTableCellMeta>{series}</AdminDataTableCellMeta> : null}
      </AdminCell>
      <AdminCell column="series">{series}</AdminCell>
      <AdminCell column="cagr" className="text-end">{percent(metrics?.cagr)}</AdminCell>
      <AdminCell column="volatility" className="text-end">{percent(metrics?.volatility)}</AdminCell>
      <AdminCell column="sharpe" className="text-end">{figure(metrics?.sharpe)}</AdminCell>
      <AdminCell column="drawdown" className="text-end">{percent(metrics?.maxDrawdown?.drawdown)}</AdminCell>
    </tr>
  );
}

function screenMessage(error: unknown): string {
  const status = typeof error === "object" && error !== null && "status" in error ? Number((error as { status: unknown }).status) : 0;
  if (status === 404) return "That screen is not stored.";
  return "The screen could not be loaded.";
}

function sortRows(rows: readonly ScreenRow[], sort: SortKey): ScreenRow[] {
  return [...rows].sort((left, right) => {
    if (sort === "symbol") return left.symbol.localeCompare(right.symbol);
    if (sort === "composite") return (right.composite ?? 0) - (left.composite ?? 0);
    return left.rank - right.rank;
  });
}

function curve(name: string, colour: string, labels: readonly string[], values: readonly number[]) {
  return {
    name,
    colour,
    points: values.map((y, index) => ({ x: labels[index] ?? String(index), y })),
  };
}

function figure(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}

function percent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}
