import { useId, useState } from "react";
import {
  AdminCell,
  AdminDataTable,
  AdminDataTableCellMeta,
  type AdminDataTableColumn,
} from "../components/ui/AdminDataTable";
import { ConfirmDialog, DateTimeDisplay } from "../components/ui";
import { useApiKeys, useJobRuns, useRunJob, useSystemStatus, useUniverse, type JobRun } from "../hooks/useSystemStatus";
import { usePutSettings, type Settings } from "../hooks/useSettings";
import { accessLabel } from "../lib/apiKeyDisplay";
import { methodology } from "../lib/contracts/generated";

type SwitchName = keyof Settings;

const registerSize = methodology.backtest.portfolioSize;
const MIN_NAMES = 10;
const MAX_NAMES = 40;

function chosenSize(text: string): number | null {
  if (!/^\d+$/.test(text)) return null;
  const value = Number(text);
  if (value < MIN_NAMES || value > MAX_NAMES) return null;
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
  const sizeId = useId();
  const jobs = [...(status.data?.jobs ?? [])].sort((left, right) => Number(right.lastRun?.status === "failed") - Number(left.lastRun?.status === "failed"));
  const columns: AdminDataTableColumn[] = [
    { key: "job", header: "Job" },
    { key: "schedule", header: "Schedule" },
    { key: "status", header: "Last status" },
    { key: "started", header: "Started" },
    { key: "duration", header: "Duration" },
    { key: "message", header: "Message" },
    { key: "run", header: "Run" },
  ];
  const data = universe.data;
  const coverage = {
    ...(data?.coverage?.flows ?? {}),
    ...(data?.coverage?.stocks ?? {}),
    ...(data?.coverage?.shareFlows ?? {}),
  };

  return (
    <div>
      <h2 className="h5">Switches</h2>
      <table className="table">
        <thead>
          <tr><th>Name</th><th>Parameter</th><th>Setting</th><th>Effective</th></tr>
        </thead>
        <tbody>
          {(status.data?.switches ?? []).map((item) => (
            <tr key={item.name}>
              <td>{item.name}</td>
              <td>
                {String(item.parameter)}
                <div className="small text-body-secondary">Change in the parameter file and redeploy</div>
              </td>
              <td>
                <button
                  type="button"
                  className="btn btn-sm btn-outline-secondary"
                  aria-label={`${item.name} setting`}
                  onClick={() => setPending({ name: item.name as SwitchName, next: !item.setting })}
                >
                  {item.setting ? "On" : "Off"}
                </button>
                {!item.parameter ? <div className="small">The setting has no effect until the parameter is on.</div> : null}
              </td>
              <td>{String(item.effective)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>Broker mode <span className="badge text-bg-secondary">{status.data?.brokerMode ?? "paper"}</span></p>
      <h2 className="h5">Data</h2>
      <p>
        Universe {data?.asOf ?? "—"}, {data?.members ?? 0} names. Last raw price {data?.lastPriceDate ?? "—"}.
      </p>
      <table className="table">
        <caption>Count after each rule</caption>
        <thead><tr><th>Rule</th><th>Count</th></tr></thead>
        <tbody>
          {Object.entries(data?.counts ?? {}).map(([rule, count]) => (
            <tr key={rule}><td>{rule}</td><td>{count}</td></tr>
          ))}
        </tbody>
      </table>
      <table className="table">
        <caption>Fundamentals coverage</caption>
        <thead><tr><th>Field</th><th>Share</th></tr></thead>
        <tbody>
          {Object.entries(coverage).map(([field, share]) => (
            <tr key={field}><td>{field}</td><td>{percent(share)}</td></tr>
          ))}
        </tbody>
      </table>
      <p>
        Price backfill {progress(data?.backfill?.prices)}. Fundamentals backfill {progress(data?.backfill?.fundamentals)}.
      </p>
      <h2 className="h5">Jobs</h2>
      {accepted ? <p role="status">Accepted {accepted}.</p> : null}
      <AdminDataTable columns={columns} bare>
        {jobs.map((job) => (
          <tr key={job.job}>
            <AdminCell column="job">
              {job.job}
              <AdminDataTableCellMeta>{statusLabel(job.lastRun?.status, job.progress)}</AdminDataTableCellMeta>
            </AdminCell>
            <AdminCell column="schedule">{job.schedule}</AdminCell>
            <AdminCell column="status">{statusLabel(job.lastRun?.status, job.progress)}</AdminCell>
            <AdminCell column="started">{job.lastRun ? <DateTimeDisplay iso={job.lastRun.startedAt} /> : "—"}</AdminCell>
            <AdminCell column="duration">{job.lastRun ? `${job.lastRun.durationMs} ms` : "—"}</AdminCell>
            <AdminCell column="message">{job.lastRun?.message ?? ""}</AdminCell>
            <AdminCell column="run">
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
            </AdminCell>
          </tr>
        ))}
      </AdminDataTable>
      <h2 className="h5">Recent runs</h2>
      <table className="table">
        <thead><tr><th>Job</th><th>Status</th><th>Started</th><th>Duration</th><th>Message</th></tr></thead>
        <tbody>
          {(runs.data?.runs ?? []).map((run: JobRun, index) => (
            <tr key={`${run.job}-${run.startedAt}-${index}`}>
              <td>{run.job}</td>
              <td>{run.status}</td>
              <td><DateTimeDisplay iso={run.startedAt} /></td>
              <td>{run.durationMs} ms</td>
              <td>{run.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2 className="h5">API keys</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Label</th><th>Tier</th><th>Scopes</th><th>Access</th><th>Created</th><th>Expires</th><th>Last used</th><th>State</th>
          </tr>
        </thead>
        <tbody>
          {(keys.data?.keys ?? []).map((row) => (
            <tr key={row.keyId} className={row.soon ? "table-warning" : undefined}>
              <td>{row.label}</td>
              <td>{row.tier}</td>
              <td>{row.scopes.join(", ")}</td>
              <td>{accessLabel(row.allowWrite, keys.data?.writesEnabled === true)}</td>
              <td><DateTimeDisplay iso={row.createdAt} /></td>
              <td>{row.expiresAt ? <DateTimeDisplay iso={row.expiresAt} /> : "never"}</td>
              <td>{row.lastUsedAt ? <DateTimeDisplay iso={row.lastUsedAt} /> : "never"}</td>
              <td>{row.state}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
          setPendingJob(null);
          runJob.mutate(size === null ? { job: name } : { job: name, portfolioSize: size }, {
            onSuccess: () => setAccepted(name),
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
              min={MIN_NAMES}
              max={MAX_NAMES}
              inputMode="numeric"
              value={names}
              onChange={(event) => setNames(event.target.value)}
            />
            <p className="form-text mb-0">10 to 40. The register uses {registerSize}.</p>
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
