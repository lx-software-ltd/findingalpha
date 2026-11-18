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
type SortDir = "asc" | "desc";

const SORT_OPTIONS: readonly { value: `${SortKey}:${SortDir}`; label: string }[] = [
  { value: "rank:asc", label: "Rank, low to high" },
  { value: "rank:desc", label: "Rank, high to low" },
  { value: "symbol:asc", label: "Symbol, A to Z" },
  { value: "symbol:desc", label: "Symbol, Z to A" },
  { value: "composite:desc", label: "Composite, high to low" },
  { value: "composite:asc", label: "Composite, low to high" },
];

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
  const [direction, setDirection] = useState<SortDir>("asc");
  const [open, setOpen] = useState("");
  const screen = useScreen(requested);
  const rows = useMemo(
    () => sortRows(screen.data?.rows ?? [], sort, direction),
    [screen.data, sort, direction],
  );
  const factorNames = Object.keys(rows[0]?.factors ?? {});

  function chooseSort(key: SortKey) {
    if (sort === key) {
      setDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSort(key);
    setDirection(key === "composite" ? "desc" : "asc");
  }

  function chooseSortValue(value: string) {
    const [key, dir] = value.split(":");
    if (key !== "rank" && key !== "symbol" && key !== "composite") return;
    if (dir !== "asc" && dir !== "desc") return;
    setSort(key);
    setDirection(dir);
  }

  const columns = shortlistColumns(factorNames, sort, direction, chooseSort);

  return (
    <div>
      {screen.isError ? <div className="alert alert-danger" role="alert">{screenMessage(screen.error)}</div> : null}
      <div className="admin-kpi-row">
        <AdminKpi label="Date" value={screen.data?.asOf ?? "—"} />
        <AdminKpi label="Universe" value={screen.data?.counts.universe ?? "—"} />
        <AdminKpi label="Passed" value={screen.data?.counts.passed ?? "—"} />
        <AdminKpi label="Shortlisted" value={screen.data?.counts.shortlisted ?? "—"} />
      </div>
      <AdminRecordTable
        label="Shortlist"
        beforeTable={
          <p className="small text-muted font-monospace mb-0">Register hash {screen.data?.registerHash ?? "—"}</p>
        }
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
              <AdminFilterField label="Date" htmlFor="screen-date" className="admin-filter-field-compact">
                <input
                  id="screen-date"
                  className="form-control form-control-sm"
                  type="date"
                  value={date}
                  onChange={(event) => setDate(event.target.value)}
                />
              </AdminFilterField>
              <AdminFilterField label="Sort" htmlFor="screen-sort" className="d-md-none admin-filter-field-full">
                <select
                  id="screen-sort"
                  className="form-select form-select-sm"
                  value={`${sort}:${direction}`}
                  onChange={(event) => chooseSortValue(event.target.value)}
                >
                  {SORT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
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
  direction: SortDir,
  chooseSort: (key: SortKey) => void,
): AdminDataTableColumn[] {
  const sortHeader = (key: SortKey, label: string): AdminDataTableColumn => ({
    key,
    header: (
      <TableSortHeaderButton
        label={label}
        isActive={sort === key}
        direction={sort === key ? direction : null}
        onClick={() => chooseSort(key)}
        align={key === "rank" || key === "composite" ? "end" : "start"}
      />
    ),
    thAriaSort: sort === key ? (direction === "asc" ? "ascending" : "descending") : "none",
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
        <span className="fw-semibold">{row.symbol}</span>
        <AdminDataTableCellMeta>
          Rank {row.rank} · {row.name} · {figure(row.composite)}
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
      <div className="col-6 col-md-4">Sector: {row.sector}</div>
      <div className="col-6 col-md-4">Quality: {figure(row.groups.quality)}</div>
      <div className="col-6 col-md-4">Value: {figure(row.groups.value)}</div>
      <div className="col-6 col-md-4">Trend: {figure(row.groups.trend)}</div>
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
            <AdminDataTable bare columns={metricColumns}>
              <PeriodRows name="Full" metrics={data.metrics.full} />
              <PeriodRows name="2017–2021" metrics={data.metrics.early} />
              <PeriodRows name="2022 to today" metrics={data.metrics.holdout} />
            </AdminDataTable>
          </AdminRecordTable>
          <AdminEditorSection title="Results">
            <dl className="row mb-0">
              <Stat label="Hit rate" value={percent(data.metrics.hitRate)} />
              <Stat label="Average turnover" value={percent(data.metrics.averageTurnover)} />
              <Stat label="Yearly cost drag" value={percent(data.metrics.costDrag)} />
              <Stat
                label="Worst 12 months"
                value={`${percent(data.metrics.worstWindow?.return)} (${data.metrics.worstWindow?.start ?? "—"} to ${data.metrics.worstWindow?.end ?? "—"})`}
              />
              <Stat
                label="Longest stretch behind SPY net"
                value={`${data.metrics.longestBehind?.months ?? "—"} months (${data.metrics.longestBehind?.start ?? "—"} to ${data.metrics.longestBehind?.end ?? "—"})`}
              />
              <Stat label="Names carried at a last price" value={String(data.lastPriceCount ?? "—")} />
              <Stat label="Names without a trade price" value={String(data.unpricedCount ?? "—")} />
              <Stat label="Months missing a benchmark" value={String(data.missingBenchmarkCount ?? "—")} />
            </dl>
          </AdminEditorSection>
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

function Stat({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <>
      <dt className="col-sm-5 col-lg-4">{label}</dt>
      <dd className="col-sm-7 col-lg-8">{value}</dd>
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
        {label}
        <AdminDataTableCellMeta>
          {series} · CAGR {percent(metrics?.cagr)} · Volatility {percent(metrics?.volatility)} · Sharpe {figure(metrics?.sharpe)} · Max drawdown {percent(metrics?.maxDrawdown?.drawdown)}
        </AdminDataTableCellMeta>
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

function sortRows(rows: readonly ScreenRow[], sort: SortKey, direction: SortDir): ScreenRow[] {
  const factor = direction === "asc" ? 1 : -1;
  return [...rows].sort((left, right) => {
    if (sort === "symbol") return factor * left.symbol.localeCompare(right.symbol);
    if (sort === "composite") return factor * ((left.composite ?? 0) - (right.composite ?? 0));
    return factor * (left.rank - right.rank);
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
