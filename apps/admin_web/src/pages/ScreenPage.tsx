import { useMemo, useState } from "react";
import { AdminKpi, AdminTabList, LineChart } from "../components/ui";
import {
  useBacktest,
  useBacktests,
  useScreen,
  type PeriodMetrics,
  type ScreenRow,
  type SeriesMetrics,
} from "../hooks/useScreen";

const BIASES = [
  "A name keeps the CIK from the latest universe file that still listed it. A name that was never in a stored universe file has no fundamentals, even when its prices exist.",
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

export function ScreenPage() {
  const [tab, setTab] = useState<Tab>("shortlist");
  return (
    <div>
      <h2 className="h5">Screen</h2>
      <AdminTabList
        tabs={[
          { id: "shortlist", label: "Shortlist" },
          { id: "backtest", label: "Backtest" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "shortlist" ? <Shortlist /> : <BacktestPanel />}
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

  return (
    <div>
      <form
        className="row g-2 align-items-end mb-3"
        onSubmit={(event) => {
          event.preventDefault();
          setRequested(date);
        }}
      >
        <div className="col-auto">
          <label className="form-label" htmlFor="screen-date">Date</label>
          <input id="screen-date" className="form-control" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        </div>
        <div className="col-auto">
          <button className="btn btn-outline-secondary" type="submit">Load date</button>
        </div>
      </form>
      {screen.isError ? <p>{screenMessage(screen.error)}</p> : null}
      <div className="row g-3 mb-3">
        <div className="col-6 col-lg-3"><AdminKpi label="Date" value={screen.data?.asOf ?? "—"} /></div>
        <div className="col-6 col-lg-3"><AdminKpi label="Universe" value={screen.data?.counts.universe ?? "—"} /></div>
        <div className="col-6 col-lg-3"><AdminKpi label="Passed" value={screen.data?.counts.passed ?? "—"} /></div>
        <div className="col-6 col-lg-3"><AdminKpi label="Shortlisted" value={screen.data?.counts.shortlisted ?? "—"} /></div>
      </div>
      <p className="text-break">Register hash {screen.data?.registerHash ?? "—"}</p>
      <div className="table-responsive">
        <table className="table align-middle">
          <thead>
            <tr>
              <SortHeader label="Rank" active={sort === "rank"} direction="ascending" onClick={() => setSort("rank")} />
              <SortHeader label="Symbol" active={sort === "symbol"} direction="ascending" onClick={() => setSort("symbol")} />
              <th>Name</th>
              <th>Sector</th>
              <SortHeader label="Composite" active={sort === "composite"} direction="descending" onClick={() => setSort("composite")} />
              <th>Quality</th>
              <th>Value</th>
              <th>Trend</th>
              {factorNames.map((name) => (
                <th key={name}>{name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <Row key={row.symbol} row={row} factorNames={factorNames} open={open === row.symbol} onToggle={() => setOpen(open === row.symbol ? "" : row.symbol)} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({
  row,
  factorNames,
  open,
  onToggle,
}: {
  readonly row: ScreenRow;
  readonly factorNames: readonly string[];
  readonly open: boolean;
  readonly onToggle: () => void;
}) {
  return (
    <>
      <tr>
        <td>{row.rank}</td>
        <td>
          <button type="button" className="btn btn-link p-0" onClick={onToggle}>{row.symbol}</button>
        </td>
        <td>{row.name}</td>
        <td>{row.sector}</td>
        <td>{figure(row.composite)}</td>
        <td>{figure(row.groups.quality)}</td>
        <td>{figure(row.groups.value)}</td>
        <td>{figure(row.groups.trend)}</td>
        {factorNames.map((name) => (
          <td key={name}>{figure(row.factors[name])}</td>
        ))}
      </tr>
      {open ? (
        <tr>
          <td colSpan={8 + factorNames.length}>
            <div className="row">
              {factorNames.map((name) => (
                <div className="col-6 col-md-4" key={name}>
                  {name}: {figure(row.factors[name])} (z {figure(row.z[name])})
                </div>
              ))}
            </div>
          </td>
        </tr>
      ) : null}
    </>
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
        curve("Strategy", "#0d6efd", data.labels, data.curves.strategy),
        curve("SPY net", "#6c757d", data.labels, data.curves.spyNet),
        curve("SPY gross", "#198754", data.labels, data.curves.spyGross),
      ]
    : [];
  return (
    <div>
      {runs.length === 0 ? <p>No backtest is stored. The live runs wait until prices and fundamentals are in.</p> : null}
      {runs.length > 0 ? (
        <label className="form-label">
          Run
          <select className="form-select" value={runId} onChange={(event) => setChosen(event.target.value)}>
            {runs.map((run) => (
              <option key={run.runId} value={run.runId}>{run.runId} · {run.portfolioSize} names</option>
            ))}
          </select>
        </label>
      ) : null}
      {data ? (
        <>
          <LineChart series={series} title="Backtest equity curves" formatY={(value) => value.toFixed(0)} />
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr><th>Period</th><th>Series</th><th>CAGR</th><th>Volatility</th><th>Sharpe</th><th>Max drawdown</th></tr>
              </thead>
              <tbody>
                <PeriodRows name="Full" metrics={data.metrics.full} />
                <PeriodRows name="2017–2021" metrics={data.metrics.early} />
                <PeriodRows name="2022 to today" metrics={data.metrics.holdout} />
              </tbody>
            </table>
          </div>
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
          <h3 className="h6">Yearly returns</h3>
          <ul>
            {(data.metrics.yearly ?? []).map((year) => (
              <li key={year.year}>{year.year}: strategy {percent(year.strategy)}, SPY net {percent(year.benchmark)}</li>
            ))}
          </ul>
        </>
      ) : null}
      <h3 className="h6">Known biases</h3>
      <ul>{BIASES.map((note) => <li key={note}>{note}</li>)}</ul>
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
      <td>{label}</td>
      <td>{series}</td>
      <td>{percent(metrics?.cagr)}</td>
      <td>{percent(metrics?.volatility)}</td>
      <td>{figure(metrics?.sharpe)}</td>
      <td>{percent(metrics?.maxDrawdown?.drawdown)}</td>
    </tr>
  );
}

function SortHeader({
  label,
  active,
  direction,
  onClick,
}: {
  readonly label: string;
  readonly active: boolean;
  readonly direction: "ascending" | "descending";
  readonly onClick: () => void;
}) {
  return (
    <th aria-sort={active ? direction : "none"}>
      <button type="button" className="btn btn-link p-0" onClick={onClick}>{label}</button>
    </th>
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
