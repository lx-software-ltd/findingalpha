import { AdminKpi } from "../components/ui";
import { useMethodology, type MethodologyFactor } from "../hooks/useMethodology";

function parameters(factor: MethodologyFactor): string {
  const entries = Object.entries(factor.parameters);
  if (entries.length === 0) return "—";
  return entries.map(([name, value]) => `${name} ${value}`).join(", ");
}

export function MethodologyPage() {
  const methodology = useMethodology();
  const data = methodology.data;
  const factors = data?.register.factors ?? [];
  const composite = data?.register.composite;
  const screen = data?.register.screen;

  return (
    <div>
      <h2 className="h5">Methodology</h2>
      {methodology.isError ? <p>Methodology is unavailable.</p> : null}
      <div className="row g-3 mb-4">
        <div className="col-6 col-lg-3"><AdminKpi label="Entries" value={data?.counts.entries ?? "—"} /></div>
        <div className="col-6 col-lg-3"><AdminKpi label="Provisional" value={data?.counts.provisional ?? "—"} /></div>
        <div className="col-6 col-lg-3"><AdminKpi label="Cited" value={data?.counts.cited ?? "—"} /></div>
        <div className="col-6 col-lg-3">
          <AdminKpi label="Register hash" value={<span className="text-break">{data?.hash ?? "—"}</span>} />
        </div>
      </div>
      <div className="table-responsive">
        <table className="table align-middle">
          <thead>
            <tr>
              <th>Name</th>
              <th>Group</th>
              <th>Direction</th>
              <th>Formula</th>
              <th>Parameters</th>
              <th>Status</th>
              <th>Citation</th>
            </tr>
          </thead>
          <tbody>
            {factors.map((factor) => (
              <tr key={factor.id}>
                <td>{factor.name}</td>
                <td>{factor.group}</td>
                <td>{factor.direction}</td>
                <td>{factor.formula}</td>
                <td>{parameters(factor)}</td>
                <td><span className="badge text-bg-secondary">{factor.status}</span></td>
                <td>{factor.citation?.quote ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {composite ? (
        <div className="card mb-3">
          <div className="card-body">
            <h3 className="h6">Composite</h3>
            <p className="mb-1">Status {composite.status}. Standardise {composite.standardise}.</p>
            <p className="mb-1">
              Weights {Object.entries(composite.groupWeights).map(([name, weight]) => `${name} ${weight}`).join(", ")}.
            </p>
            <p className="mb-0">
              Winsorise {composite.winsorisePercentiles.join(" to ")}. Sector minimum {composite.minSectorSize}.
              A group needs {composite.minFactorsPerGroupShare} of its factors.
            </p>
          </div>
        </div>
      ) : null}
      {screen ? (
        <div className="card">
          <div className="card-body">
            <h3 className="h6">Screen</h3>
            <p className="mb-1">Status {screen.status}. Shortlist {screen.shortlistSize}.</p>
            <ul className="mb-0">
              {screen.hardFilters.map((filter) => (
                <li key={filter.id}>{filter.field} {filter.op} {filter.value}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  );
}
