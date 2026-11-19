import { useId, useState } from "react";
import {
  AdminCell,
  AdminDataTable,
  AdminDataTableCellMeta,
  AdminDataTableEmptyRow,
  AdminKpi,
  AdminPageHeader,
  AdminRecordTable,
  ConfirmDialog,
  DateTimeDisplay,
  type AdminDataTableColumn,
} from "../components/ui";
import { useApiKeys, useJobRuns, useRunJob, useSystemStatus, useUniverse, type JobRun } from "../hooks/useSystemStatus";
import { usePutSettings, type Settings } from "../hooks/useSettings";
import { getAdminApiErrorMessage } from "../lib/apiAdminClient";
import { accessLabel } from "../lib/apiKeyDisplay";
import { methodology } from "../lib/contracts/generated";

type SwitchName = keyof Settings;

const registerSize = methodology.backtest.portfolioSize;
const minNames = methodology.backtest.portfolioSizeMin;
const maxNames = methodology.backtest.portfolioSizeMax;

function chosenSize(text: string): number | null {
  if (!/^\d+$/.test(text)) return null;
  const value = Number(text);
  if (value < minNames || value > maxNames) return null;
  return value;
}

export function SystemPage() {
  const status = useSystemStatus();
  const runs = useJobRuns();
  const keys = useApiKeys();
  const universe = useUniverse();
  const runJob = useRunJob();
  const put = usePutSettings();
  const [pending, setPending] = useState<{ name: SwitchName; next: boolean } | null>(null);
  const [pendingJob, setPendingJob] = useState<string | null>(null);
  const [names, setNames] = useState(String(registerSize));
  const [accepted, setAccepted] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const sizeId = useId();
  const jobs = [...(status.data?.jobs ?? [])].sort((left, right) => Number(right.lastRun?.status === "failed") - Number(left.lastRun?.status === "failed"));
  const columns: AdminDataTableColumn[] = [
    { key: "job", header: "Job" },
    { key: "schedule", header: "Schedule", priority: "secondary" },
    { key: "status", header: "Last status", priority: "secondary" },
    { key: "started", header: "Started", priority: "tertiary" },
    { key: "duration", header: "Duration", className: "text-end", priority: "tertiary" },
    { key: "message", header: "Message", priority: "tertiary" },
    { key: "ops", header: "Run" },
  ];
  const runColumns: AdminDataTableColumn[] = [
    { key: "job", header: "Job" },
    { key: "status", header: "Status", priority: "secondary" },
    { key: "started", header: "Started", priority: "secondary" },
    { key: "duration", header: "Duration", className: "text-end", priority: "tertiary" },
    { key: "message", header: "Message", priority: "tertiary" },
  ];
  const keyColumns: AdminDataTableColumn[] = [
    { key: "label", header: "Label" },
    { key: "tier", header: "Tier", priority: "secondary" },
    { key: "scopes", header: "Scopes", priority: "tertiary" },
    { key: "access", header: "Access", priority: "secondary" },
    { key: "created", header: "Created", priority: "tertiary" },
    { key: "expires", header: "Expires", priority: "secondary" },
    { key: "used", header: "Last used", priority: "tertiary" },
    { key: "state", header: "State", priority: "secondary" },
  ];
  const data = universe.data;
  const coverage = {
    ...(data?.coverage?.flows ?? {}),
    ...(data?.coverage?.stocks ?? {}),
    ...(data?.coverage?.shareFlows ?? {}),
  };

  return (
    <div>
      <AdminPageHeader eyebrow="Finding Alpha" title="System" />
      <h2 className="admin-card-title">Switches</h2>
      <AdminRecordTable label="Switches">
        <AdminDataTable
          bare
          columns={[
            { key: "name", header: "Name" },
            { key: "parameter", header: "Parameter", priority: "secondary" },
            { key: "effective", header: "Effective", priority: "tertiary" },
            { key: "ops", header: "Setting" },
          ]}
        >
          {(status.data?.switches ?? []).map((item) => (
            <tr key={item.name}>
              <AdminCell column="name">
                {item.name}
                <AdminDataTableCellMeta>
                  Parameter {String(item.parameter)}. Effective {String(item.effective)}.
                  <span className="d-block">Change in the parameter file and redeploy</span>
                </AdminDataTableCellMeta>
                {!item.parameter ? (
                  <div className="small text-body-secondary">The setting has no effect until the parameter is on.</div>
                ) : null}
              </AdminCell>
              <AdminCell column="parameter">
                {String(item.parameter)}
                <div className="small text-body-secondary">Change in the parameter file and redeploy</div>
              </AdminCell>
              <AdminCell column="effective">{String(item.effective)}</AdminCell>
              <AdminCell column="ops">
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary"
                  aria-label={`${item.name} setting`}
                  onClick={() => setPending({ name: item.name as SwitchName, next: !item.setting })}
                >
                  {item.setting ? "On" : "Off"}
                </button>
              </AdminCell>
            </tr>
          ))}
        </AdminDataTable>
      </AdminRecordTable>
      <div className="admin-kpi-row">
        <AdminKpi label="Broker mode" value={status.data?.brokerMode ?? "paper"} />
        <AdminKpi
          label="Universe"
          value={data ? `${data.members} names` : "—"}
          hint={data ? (data.asOf ?? "No as-of date") : undefined}
        />
        <AdminKpi label="Last price" value={data?.lastPriceDate ?? "—"} />
        <AdminKpi label="Price backfill" value={progress(data?.backfill?.prices)} />
        <AdminKpi label="Fundamentals backfill" value={progress(data?.backfill?.fundamentals)} />
      </div>
      <h2 className="admin-card-title">Data</h2>
      <AdminRecordTable label="Count after each rule">
        <AdminDataTable
          bare
          tableClassName="admin-table-keep-cols"
          columns={[
            { key: "rule", header: "Rule" },
            { key: "count", header: "Count", className: "text-end" },
          ]}
        >
          {Object.entries(data?.counts ?? {}).map(([rule, count]) => (
            <tr key={rule}>
              <AdminCell column="rule">{rule}</AdminCell>
              <AdminCell column="count" className="text-end">{count}</AdminCell>
            </tr>
          ))}
        </AdminDataTable>
      </AdminRecordTable>
      <AdminRecordTable label="Fundamentals coverage">
        <AdminDataTable
          bare
          tableClassName="admin-table-keep-cols"
          columns={[
            { key: "field", header: "Field" },
            { key: "share", header: "Share", className: "text-end" },
          ]}
        >
          {Object.entries(coverage).map(([field, share]) => (
            <tr key={field}>
              <AdminCell column="field">{field}</AdminCell>
              <AdminCell column="share" className="text-end">{percent(share)}</AdminCell>
            </tr>
          ))}
        </AdminDataTable>
      </AdminRecordTable>
      <h2 className="admin-card-title">Jobs</h2>
      {accepted ? <div className="alert alert-success" role="status">Accepted {accepted}.</div> : null}
      {runError ? <div className="alert alert-danger" role="alert">{runError}</div> : null}
      <AdminRecordTable label="Jobs">
        <AdminDataTable columns={columns} bare>
          {jobs.map((job) => (
            <tr key={job.job}>
              <AdminCell column="job">
                {job.job}
                <AdminDataTableCellMeta>
                  {job.schedule || "—"} · {statusLabel(job.lastRun?.status, job.progress)}
                </AdminDataTableCellMeta>
                <AdminDataTableCellMeta until="tertiary">
                  {job.lastRun ? <DateTimeDisplay iso={job.lastRun.startedAt} /> : "—"}
                  {" · "}
                  {job.lastRun ? `${job.lastRun.durationMs} ms` : "—"}
                </AdminDataTableCellMeta>
                {job.lastRun?.message ? (
                  <AdminDataTableCellMeta until="tertiary">{job.lastRun.message}</AdminDataTableCellMeta>
                ) : null}
              </AdminCell>
              <AdminCell column="schedule">{job.schedule}</AdminCell>
              <AdminCell column="status">{statusLabel(job.lastRun?.status, job.progress)}</AdminCell>
              <AdminCell column="started">{job.lastRun ? <DateTimeDisplay iso={job.lastRun.startedAt} /> : "—"}</AdminCell>
              <AdminCell column="duration" className="text-end">{job.lastRun ? `${job.lastRun.durationMs} ms` : "—"}</AdminCell>
              <AdminCell column="message">{job.lastRun?.message ?? ""}</AdminCell>
              <AdminCell column="ops">
                <div className="d-grid gap-1">
                  {job.manualRun ? (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-primary"
                      onClick={() => {
                        setNames(String(registerSize));
                        setPendingJob(job.job);
                      }}
                    >
                      Run now
                    </button>
                  ) : null}
                </div>
              </AdminCell>
            </tr>
          ))}
        </AdminDataTable>
      </AdminRecordTable>
      <h2 className="admin-card-title">Recent runs</h2>
      <AdminRecordTable label="Recent runs">
        <AdminDataTable
          bare
          columns={runColumns}
        >
          {(runs.data?.runs ?? []).length === 0 ? (
            <AdminDataTableEmptyRow colSpan={runColumns.length} message="No runs yet." />
          ) : (
            (runs.data?.runs ?? []).map((run: JobRun, index) => (
              <tr key={`${run.job}-${run.startedAt}-${index}`}>
                <AdminCell column="job">
                  {run.job}
                  <AdminDataTableCellMeta>
                    {run.status} · <DateTimeDisplay iso={run.startedAt} />
                  </AdminDataTableCellMeta>
                  <AdminDataTableCellMeta until="tertiary">{run.durationMs} ms</AdminDataTableCellMeta>
                  {run.message ? <AdminDataTableCellMeta until="tertiary">{run.message}</AdminDataTableCellMeta> : null}
                </AdminCell>
                <AdminCell column="status">{run.status}</AdminCell>
                <AdminCell column="started"><DateTimeDisplay iso={run.startedAt} /></AdminCell>
                <AdminCell column="duration" className="text-end">{run.durationMs} ms</AdminCell>
                <AdminCell column="message">{run.message}</AdminCell>
              </tr>
            ))
          )}
        </AdminDataTable>
      </AdminRecordTable>
      <h2 className="admin-card-title">API keys</h2>
      <AdminRecordTable label="API keys">
        <AdminDataTable
          bare
          columns={keyColumns}
        >
          {(keys.data?.keys ?? []).length === 0 ? (
            <AdminDataTableEmptyRow colSpan={keyColumns.length} message="No keys yet." />
          ) : (
            (keys.data?.keys ?? []).map((row) => (
              <tr key={row.keyId} className={row.soon ? "table-warning" : undefined}>
                <AdminCell column="label">
                  {row.label}
                  <AdminDataTableCellMeta>
                    {row.state} · {row.tier} · {accessLabel(row.allowWrite, keys.data?.writesEnabled === true)} · expires{" "}
                    {row.expiresAt ? <DateTimeDisplay iso={row.expiresAt} /> : "never"}
                  </AdminDataTableCellMeta>
                  <AdminDataTableCellMeta until="tertiary">{row.scopes.join(", ")}</AdminDataTableCellMeta>
                  <AdminDataTableCellMeta until="tertiary">
                    Created <DateTimeDisplay iso={row.createdAt} />
                    {" · "}
                    Last used {row.lastUsedAt ? <DateTimeDisplay iso={row.lastUsedAt} /> : "never"}
                  </AdminDataTableCellMeta>
                </AdminCell>
                <AdminCell column="tier">{row.tier}</AdminCell>
                <AdminCell column="scopes">{row.scopes.join(", ")}</AdminCell>
                <AdminCell column="access">{accessLabel(row.allowWrite, keys.data?.writesEnabled === true)}</AdminCell>
                <AdminCell column="created"><DateTimeDisplay iso={row.createdAt} /></AdminCell>
                <AdminCell column="expires">{row.expiresAt ? <DateTimeDisplay iso={row.expiresAt} /> : "never"}</AdminCell>
                <AdminCell column="used">{row.lastUsedAt ? <DateTimeDisplay iso={row.lastUsedAt} /> : "never"}</AdminCell>
                <AdminCell column="state">{row.state}</AdminCell>
              </tr>
            ))
          )}
        </AdminDataTable>
      </AdminRecordTable>
      <p className="small text-body-secondary">Keys are created and revoked with the Manage Public API Keys workflow.</p>
      <ConfirmDialog
        open={pendingJob !== null}
        title="Run job"
        body={pendingJob ? `Run ${pendingJob} now?` : ""}
        confirmLabel="Run"
        confirmDisabled={pendingJob === "backtest" && chosenSize(names) === null}
        onCancel={() => setPendingJob(null)}
        onConfirm={() => {
          if (!pendingJob) return;
          const name = pendingJob;
          const size = name === "backtest" ? chosenSize(names) : null;
          if (name === "backtest" && size === null) return;
          const explicit = size !== null && size !== registerSize ? size : null;
          setPendingJob(null);
          runJob.mutate(explicit === null ? { job: name } : { job: name, portfolioSize: explicit }, {
            onSuccess: (result) => {
              if (explicit !== null && result.portfolioSize !== explicit) {
                setAccepted(null);
                setRunError(`The server did not confirm ${explicit} names. The run may use the register size.`);
                return;
              }
              setRunError(null);
              setAccepted(explicit === null ? name : `${name}, ${explicit} names`);
            },
            onError: (error: unknown) => {
              setAccepted(null);
              setRunError(getAdminApiErrorMessage(error) ?? "The run was refused.");
            },
          });
        }}
      >
        {pendingJob === "backtest" ? (
          <div className="mb-3">
            <label htmlFor={sizeId} className="form-label">
              Names
            </label>
            <input
              id={sizeId}
              className="form-control form-control-sm"
              type="number"
              min={minNames}
              max={maxNames}
              inputMode="numeric"
              value={names}
              onChange={(event) => setNames(event.target.value)}
            />
            <p className="form-text mb-0">
              {minNames} to {maxNames}. Leave {registerSize} to use the register.
            </p>
          </div>
        ) : null}
      </ConfirmDialog>
      <ConfirmDialog
        open={pending !== null}
        title="Change setting"
        body={pending ? `Turn ${pending.name} ${pending.next ? "on" : "off"}?` : ""}
        confirmLabel="Save"
        onCancel={() => setPending(null)}
        onConfirm={() => {
          if (!pending) return;
          put.mutate({ [pending.name]: pending.next });
          setPending(null);
        }}
      />
    </div>
  );
}

function statusLabel(
  status: string | undefined,
  row: { cursor: number; total: number } | null | undefined,
): string {
  const name = status ?? "never";
  if (!row || row.total <= 0) return name;
  return `${name} · ${row.cursor} of ${row.total}`;
}

function progress(row: { cursor: number; total: number } | null | undefined): string {
  if (!row || row.total === 0) return "—";
  return `${row.cursor} of ${row.total}`;
}

function percent(share: number | null | undefined): string {
  if (typeof share !== "number" || Number.isNaN(share)) return "—";
  return `${Math.round(share * 1000) / 10}%`;
}
