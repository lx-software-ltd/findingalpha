import { useMemo } from "react";
import {
  AdminCell,
  AdminDataTable,
  AdminDataTableCellMeta,
  AdminEditorSection,
  AdminKpi,
  AdminPageHeader,
  AdminRecordTable,
  type AdminDataTableColumn,
} from "../components/ui";
import { useMethodology, type MethodologyFactor } from "../hooks/useMethodology";

function parameters(factor: MethodologyFactor): string {
  const entries = Object.entries(factor.parameters);
  if (entries.length === 0) return "—";
  return entries.map(([name, value]) => `${name} ${value}`).join(", ");
}

const COLUMNS: readonly AdminDataTableColumn[] = [
  { key: "name", header: "Name" },
  { key: "group", header: "Group", priority: "secondary" },
  { key: "direction", header: "Direction", priority: "tertiary" },
  { key: "formula", header: "Formula", priority: "secondary" },
  { key: "parameters", header: "Parameters", priority: "tertiary" },
  { key: "status", header: "Status", priority: "secondary" },
  { key: "citation", header: "Citation", priority: "tertiary" },
];

export function MethodologyPage() {
  const methodology = useMethodology();
  const data = methodology.data;
  const factors = data?.register.factors ?? [];
  const composite = data?.register.composite;
  const screen = data?.register.screen;
  const columns = useMemo(() => COLUMNS, []);

  return (
    <div>
      <AdminPageHeader eyebrow="Finding Alpha" title="Methodology" />
      {methodology.isError ? <p>Methodology is unavailable.</p> : null}
      <div className="admin-kpi-row">
        <AdminKpi label="Entries" value={data?.counts.entries ?? "—"} />
        <AdminKpi label="Provisional" value={data?.counts.provisional ?? "—"} />
        <AdminKpi label="Cited" value={data?.counts.cited ?? "—"} />
        <AdminKpi label="Register hash" value={<span className="text-break">{data?.hash ?? "—"}</span>} />
      </div>
      <h2 className="admin-card-title">Factors</h2>
      <AdminRecordTable label="Factors">
        <AdminDataTable bare columns={columns}>
          {factors.map((factor) => (
            <tr key={factor.id}>
              <AdminCell column="name">
                {factor.name}
                <AdminDataTableCellMeta>
                  {factor.group} · <span className="badge text-bg-secondary">{factor.status}</span>
                </AdminDataTableCellMeta>
              </AdminCell>
              <AdminCell column="group">{factor.group}</AdminCell>
              <AdminCell column="direction">{factor.direction}</AdminCell>
              <AdminCell column="formula">{factor.formula}</AdminCell>
              <AdminCell column="parameters">{parameters(factor)}</AdminCell>
              <AdminCell column="status"><span className="badge text-bg-secondary">{factor.status}</span></AdminCell>
              <AdminCell column="citation">{factor.citation?.quote ?? "—"}</AdminCell>
            </tr>
          ))}
        </AdminDataTable>
      </AdminRecordTable>
      {composite ? (
        <AdminEditorSection title="Composite">
          <p className="mb-1">Status {composite.status}. Standardise {composite.standardise}.</p>
          <p className="mb-1">
            Weights {Object.entries(composite.groupWeights).map(([name, weight]) => `${name} ${weight}`).join(", ")}.
          </p>
          <p className="mb-0">
            Winsorise {composite.winsorisePercentiles.join(" to ")}. Sector minimum {composite.minSectorSize}.
            A group needs {composite.minFactorsPerGroupShare} of its factors.
          </p>
        </AdminEditorSection>
      ) : null}
      {screen ? (
        <AdminEditorSection title="Screen">
          <p className="mb-1">Status {screen.status}. Shortlist {screen.shortlistSize}.</p>
          <ul className="mb-0">
            {screen.hardFilters.map((filter) => (
              <li key={filter.id}>{filter.field} {filter.op} {filter.value}</li>
            ))}
          </ul>
        </AdminEditorSection>
      ) : null}
    </div>
  );
}
