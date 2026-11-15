import { useState } from "react";
import { AdminCell, AdminDataTable, type AdminDataTableColumn } from "../components/ui/AdminDataTable";
import { ConfirmDialog, DateTimeDisplay } from "../components/ui";
import { useApiKeys, useJobRuns, useSystemStatus, type JobRun } from "../hooks/useSystemStatus";
import { usePutSettings, type Settings } from "../hooks/useSettings";
import { accessLabel } from "../lib/apiKeyDisplay";

type SwitchName = keyof Settings;

export function SystemPage() {
  const status = useSystemStatus();
  const runs = useJobRuns();
  const keys = useApiKeys();
  const put = usePutSettings();
  const [pending, setPending] = useState<{ name: SwitchName; next: boolean } | null>(null);
  const jobs = [...(status.data?.jobs ?? [])].sort((left, right) => Number(right.lastRun?.status === "failed") - Number(left.lastRun?.status === "failed"));
  const columns: AdminDataTableColumn[] = [
    { key: "job", header: "Job" },
    { key: "schedule", header: "Schedule" },
    { key: "status", header: "Last status" },
    { key: "started", header: "Started" },
    { key: "duration", header: "Duration" },
    { key: "message", header: "Message" },
  ];

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
      <h2 className="h5">Jobs</h2>
      <AdminDataTable columns={columns} bare>
        {jobs.map((job) => (
          <tr key={job.job}>
            <AdminCell column="job">{job.job}</AdminCell>
            <AdminCell column="schedule">{job.schedule}</AdminCell>
            <AdminCell column="status">{job.lastRun?.status ?? "never"}</AdminCell>
            <AdminCell column="started">{job.lastRun ? <DateTimeDisplay iso={job.lastRun.startedAt} /> : "—"}</AdminCell>
            <AdminCell column="duration">{job.lastRun ? `${job.lastRun.durationMs} ms` : "—"}</AdminCell>
            <AdminCell column="message">{job.lastRun?.message ?? ""}</AdminCell>
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
