import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AdminKpi, ConfirmDialog, DateTimeDisplay } from "../components/ui";
import { useRunJob } from "../hooks/useSystemStatus";
import {
  useKnowledgeBaseEvaluation,
  useKnowledgeBaseStatus,
  useSyncKnowledgeBase,
  type KnowledgeBaseProblem,
} from "../hooks/useKnowledgeBase";
import { getAdminApiErrorMessage } from "../lib/apiAdminClient";
import { queryKeys } from "../lib/queryKeys";

const PROBLEM_LABEL: Record<string, string> = {
  too_large: "larger than 50 MB",
  unsupported: "unsupported type",
  sidecar_too_large: "sidecar larger than 10 KB",
  orphan_sidecar: "sidecar without its document",
};

type Action = "sync" | "eval" | "confirm" | "stop";

export function KnowledgeBasePage() {
  const client = useQueryClient();
  const status = useKnowledgeBaseStatus();
  const evaluation = useKnowledgeBaseEvaluation();
  const sync = useSyncKnowledgeBase();
  const runEval = useRunJob();
  const [action, setAction] = useState<Action | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const data = status.data;
  const blockedDeletion = data?.blocked?.status === "blocked_deletion";
  const blockedSize = data?.blocked?.status === "blocked_size";
  const canSync = data != null && !data.running && !data.stopping && !blockedDeletion && !blockedSize;

  function finish(message: string) {
    setNotice(message);
    setError(null);
  }

  function fail(caught: unknown) {
    setNotice(null);
    setError(getAdminApiErrorMessage(caught) ?? "The request was refused.");
  }

  return (
    <div>
      <h2 className="h5">Knowledge base</h2>
      {status.isError ? <p>The knowledge base is unavailable.</p> : null}
      {status.isLoading ? <p>Loading the knowledge base.</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <div className="row g-3 mb-4">
        <div className="col-6 col-lg-4">
          <AdminKpi
            label="Documents"
            value={data?.documents ?? "—"}
            hint={data?.running ? "from the last finished sync" : undefined}
          />
        </div>
        <div className="col-6 col-lg-4">
          <AdminKpi
            label="Size"
            value={data ? gigabytes(data.bytes) : "—"}
            hint={sizeHint(data)}
          />
          {data ? <Meter label="Size against the cap" used={data.bytes} cap={data.capBytes} /> : null}
        </div>
        <div className="col-6 col-lg-4">
          <AdminKpi
            label="Retrievals this month"
            value={data ? data.retrievals.toLocaleString("en-US") : "—"}
            hint={data ? `of ${data.retrievalCap.toLocaleString("en-US")}` : undefined}
          />
          {data ? <Meter label="Retrievals against the cap" used={data.retrievals} cap={data.retrievalCap} /> : null}
        </div>
        <div className="col-6 col-lg-4">
          <AdminKpi
            label="Last sync"
            value={data?.syncedAt ? <DateTimeDisplay iso={data.syncedAt} /> : "—"}
            hint={data ? syncLabel(data.status, data.running, data.stopping) : undefined}
          />
        </div>
        <div className="col-6 col-lg-4">
          <AdminKpi
            label="Evaluation"
            value={hits(data?.evaluation.hitAt8, data?.evaluation.questions)}
            hint={data?.evaluation.hitAt3 == null ? undefined : `${data.evaluation.hitAt3} of ${data.evaluation.questions} in the top 3`}
          />
        </div>
        <div className="col-6 col-lg-4">
          <AdminKpi
            label="Storage for a month"
            value={data ? dollars(data.cost.storageUsd) : "—"}
            hint={data ? "at the current size" : undefined}
          />
        </div>
        <div className="col-6 col-lg-4">
          <AdminKpi
            label="Retrievals so far"
            value={data ? dollars(data.cost.retrievalUsd) : "—"}
            hint={data ? "this month" : undefined}
          />
        </div>
      </div>
      <div className="d-flex flex-wrap gap-2 mb-4">
        {canSync ? (
          <button type="button" className="btn btn-primary" onClick={() => setAction("sync")}>Sync now</button>
        ) : null}
        <button type="button" className="btn btn-outline-primary" onClick={() => setAction("eval")}>Run evaluation</button>
        {blockedDeletion ? (
          <button type="button" className="btn btn-outline-danger" onClick={() => setAction("confirm")}>
            Confirm deletion
          </button>
        ) : null}
        {data?.running && !data.stopping ? (
          <button type="button" className="btn btn-outline-secondary" onClick={() => setAction("stop")}>Stop</button>
        ) : null}
      </div>
      {data && !data.syncedAt ? <p>The first sync has not finished.</p> : null}
      {data?.running ? <p>{progressSentence(data.progress)}</p> : null}
      {data?.blockedReason ? <p>{data.blockedReason}</p> : null}
      {data?.stopping ? <p>Stopping the sync.</p> : null}
      <h3 className="h6">Problems</h3>
      {status.isSuccess && data && data.problems.length === 0 && data.failedDocuments.length === 0 ? (
        <p>No problem files.</p>
      ) : null}
      <ProblemList problems={data?.problems ?? []} failed={data?.failedDocuments ?? []} />
      <h3 className="h6">Evaluation</h3>
      {evaluation.isError ? <p>The evaluation is unavailable.</p> : null}
      {evaluation.isSuccess && evaluation.data.results.length === 0 ? <p>No evaluation has run.</p> : null}
      <div className="table-responsive">
        <table className="table">
          <thead><tr><th>Question</th><th>Hit rank</th></tr></thead>
          <tbody>
            {(evaluation.data?.results ?? []).map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td>{row.rank ?? "miss"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ConfirmDialog
        open={action !== null}
        title={dialogTitle(action)}
        body={dialogBody(action)}
        confirmLabel={dialogConfirm(action)}
        tone={action === "confirm" || action === "stop" ? "danger" : "primary"}
        onCancel={() => setAction(null)}
        onConfirm={() => {
          const chosen = action;
          setAction(null);
          if (chosen === "eval") {
            runEval.mutate(
              { job: "kb_eval" },
              {
                onSuccess: () => {
                  finish("Evaluation started.");
                  void client.invalidateQueries({ queryKey: queryKeys.knowledgeBase });
                  void client.invalidateQueries({ queryKey: queryKeys.knowledgeBaseEval });
                },
                onError: fail,
              },
            );
            return;
          }
          const body = chosen === "confirm" ? { confirmDeletion: true } : chosen === "stop" ? { stop: true } : undefined;
          sync.mutate(body, { onSuccess: () => finish(syncNotice(chosen)), onError: fail });
        }}
      />
    </div>
  );
}

function ProblemList({
  problems,
  failed,
}: {
  readonly problems: readonly KnowledgeBaseProblem[];
  readonly failed: readonly string[];
}) {
  if (problems.length === 0 && failed.length === 0) return null;
  return (
    <ul>
      {problems.map((item) => (
        <li key={`${item.problem}-${item.key}`}>{item.key}: {PROBLEM_LABEL[item.problem] ?? item.problem}</li>
      ))}
      {failed.map((key) => (
        <li key={key}>{key}: failed during sync</li>
      ))}
    </ul>
  );
}

function Meter({ label, used, cap }: { readonly label: string; readonly used: number; readonly cap: number | null }) {
  const share = cap && cap > 0 ? Math.min(100, Math.round((used / cap) * 100)) : 0;
  return (
    <div className="progress mb-3" role="progressbar" aria-label={label} aria-valuenow={share} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-bar" style={{ width: `${share}%` }} />
    </div>
  );
}

function gigabytes(bytes: number): string {
  return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
}

function dollars(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

function hits(found: number | null | undefined, questions: number | undefined): string {
  if (found == null || !questions) return "—";
  return `${found} of ${questions} in the top 8`;
}

function sizeHint(data: { capBytes: number | null; running: boolean } | undefined): string | undefined {
  if (!data) return undefined;
  const parts = [
    data.capBytes ? `of ${gigabytes(data.capBytes)}` : "",
    data.running ? "from the last finished sync" : "",
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(", ") : undefined;
}

const STATUS_LABEL: Record<string, string> = {
  never: "not synced",
  done: "finished",
  failed: "failed",
  unchanged: "unchanged",
  blocked_deletion: "waiting for confirmation",
  blocked_size: "over the size cap",
  running: "running",
  stopping: "stopping",
};

function syncLabel(status: string, running: boolean, stopping: boolean): string {
  if (stopping) return "stopping";
  if (running) return "running";
  return STATUS_LABEL[status] ?? status.replaceAll("_", " ");
}

function progressSentence(
  progress: { readonly scanned: number; readonly indexed: number; readonly failed: number } | null,
): string {
  if (!progress) return "Progress appears after the next check.";
  const failed = progress.failed > 0 ? `, ${progress.failed.toLocaleString("en-US")} failed` : "";
  const scanned = progress.scanned.toLocaleString("en-US");
  const indexed = progress.indexed.toLocaleString("en-US");
  return `Scanned ${scanned}, indexed ${indexed}${failed}.`;
}

function dialogTitle(action: Action | null): string {
  if (action === "eval") return "Run evaluation";
  if (action === "confirm") return "Confirm deletion";
  if (action === "stop") return "Stop sync";
  return "Sync now";
}

function dialogBody(action: Action | null): string {
  if (action === "eval") return "Score the questions file against the knowledge base?";
  if (action === "confirm") return "More than 15% of a folder is gone. Sync anyway?";
  if (action === "stop") return "Stop the knowledge base sync that is running?";
  return "Start a knowledge base sync?";
}

function dialogConfirm(action: Action | null): string {
  if (action === "eval") return "Start evaluation";
  if (action === "confirm") return "Sync";
  if (action === "stop") return "Stop sync";
  return "Sync";
}

function syncNotice(action: Action | null): string {
  if (action === "confirm") return "Deletion confirmed. The sync was requested.";
  if (action === "stop") return "Stop requested.";
  return "Sync requested.";
}
