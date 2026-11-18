import { useState } from "react";
import {
  AdminCell,
  AdminDataTable,
  AdminDataTableCellMeta,
  AdminEditorSection,
  AdminExpandableRow,
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
  const [open, setOpen] = useState("");

  return (
    <div>
      <AdminPageHeader eyebrow="Finding Alpha" title="Methodology" />
      {methodology.isError ? <div className="alert alert-danger" role="alert">Methodology is unavailable.</div> : null}
      <div className="admin-kpi-row">
        <AdminKpi label="Entries" value={data?.counts.entries ?? "—"} />
        <AdminKpi label="Provisional" value={data?.counts.provisional ?? "—"} />
        <AdminKpi label="Cited" value={data?.counts.cited ?? "—"} />
      </div>
      <h2 className="admin-card-title">Factors</h2>
      <AdminRecordTable
        label="Factors"
        beforeTable={<p className="small text-muted font-monospace mb-0">Register hash {data?.hash ?? "—"}</p>}
      >
        <AdminDataTable bare columns={COLUMNS}>
          {factors.map((factor) => (
            <FactorRow
              key={factor.id}
              factor={factor}
              open={open === factor.id}
              onToggle={() => setOpen(open === factor.id ? "" : factor.id)}
            />
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

function FactorRow({
  factor,
  open,
  onToggle,
}: {
  readonly factor: MethodologyFactor;
  readonly open: boolean;
  readonly onToggle: () => void;
}) {
  return (
    <AdminExpandableRow
      colSpan={COLUMNS.length}
      expanded={open}
      onToggle={onToggle}
      editor={
        <dl className="row mb-0">
          <dt className="col-sm-3">Direction</dt>
          <dd className="col-sm-9">{factor.direction}</dd>
          <dt className="col-sm-3">Formula</dt>
          <dd className="col-sm-9">{factor.formula}</dd>
          <dt className="col-sm-3">Parameters</dt>
          <dd className="col-sm-9">{parameters(factor)}</dd>
          <dt className="col-sm-3">Citation</dt>
          <dd className="col-sm-9">{factor.citation?.quote ?? "—"}</dd>
        </dl>
      }
    >
      <AdminCell column="name">
        <span className="fw-semibold">{factor.name}</span>
        <AdminDataTableCellMeta>
          {factor.group} · <span className="badge text-bg-secondary">{factor.status}</span>
        </AdminDataTableCellMeta>
        <AdminDataTableCellMeta until="secondary">{factor.formula}</AdminDataTableCellMeta>
      </AdminCell>
      <AdminCell column="group">{factor.group}</AdminCell>
      <AdminCell column="direction">{factor.direction}</AdminCell>
      <AdminCell column="formula">{factor.formula}</AdminCell>
      <AdminCell column="parameters">{parameters(factor)}</AdminCell>
      <AdminCell column="status"><span className="badge text-bg-secondary">{factor.status}</span></AdminCell>
      <AdminCell column="citation">{factor.citation?.quote ?? "—"}</AdminCell>
    </AdminExpandableRow>
  );
}

(FactorRow as { recordGroup?: boolean }).recordGroup = true;
