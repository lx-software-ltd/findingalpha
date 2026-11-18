import { ROADMAP } from "../lib/contracts/generated";
import { useOwnerTasks, useSetOwnerTask } from "../hooks/useOwnerTasks";
import { AdminKpi, AdminPageHeader } from "../components/ui";
import {
  blockingOwnerTasks,
  currentMilestone,
  milestoneProgress,
  overallProgress,
  planUrl,
  stepStatus,
  type RoadmapFile,
  type RoadmapMilestone,
} from "../lib/roadmapModel";

const roadmap = ROADMAP as unknown as RoadmapFile;

const STATUS_CLASS: Record<string, string> = {
  not_started: "text-bg-secondary",
  in_progress: "text-bg-primary",
  blocked: "text-bg-warning",
  done: "text-bg-success",
};

function MilestoneCard({
  milestone,
  doneIds,
}: {
  readonly milestone: RoadmapMilestone;
  readonly doneIds: ReadonlySet<string>;
}) {
  const progress = milestoneProgress(milestone);
  const blockers = blockingOwnerTasks(milestone, roadmap, doneIds);
  return (
    <article className="card shadow-sm mb-3">
      <div className="card-body">
        <div className="d-flex flex-wrap gap-2 align-items-center">
          <span className="badge text-bg-light border">{milestone.id}</span>
          <h3 className="admin-card-title mb-0">{milestone.title}</h3>
          <span className={`badge ${STATUS_CLASS[milestone.status] ?? "text-bg-secondary"}`}>{milestone.status}</span>
          <span className="badge text-bg-light border">{milestone.zone}</span>
        </div>
        <div className="progress my-2" role="progressbar" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-bar" style={{ width: `${progress.percent}%` }} />
        </div>
        {blockers.length > 0 ? <p className="text-warning-emphasis mb-1">Blocked by {blockers.map((task) => task.id).join(", ")}</p> : null}
        <a href={planUrl(milestone)}>Plan</a>
        {(milestone.pullRequests ?? []).map((url) => (
          <a key={url} href={url} className="ms-2">Pull request</a>
        ))}
        <details className="admin-disclosure mt-2">
          <summary>Steps</summary>
          <ul className="list-unstyled mb-0">
            {milestone.steps.map((step) => (
              <li key={step.id}>
                <span className="me-2">{stepStatus(step.status)}</span>
                {step.id} {step.title}
              </li>
            ))}
          </ul>
        </details>
      </div>
    </article>
  );
}

export function RoadmapPage() {
  const tasks = useOwnerTasks();
  const setTask = useSetOwnerTask();
  const done = tasks.data?.done ?? {};
  const doneIds = new Set(Object.keys(done));
  const progress = overallProgress(roadmap);
  const current = currentMilestone(roadmap);
  const milestonesDone = roadmap.milestones.filter((milestone) => milestone.status === "done").length;
  const openTasks = roadmap.ownerTasks.filter((task) => !doneIds.has(task.id));
  const currentBlockers = current ? new Set(blockingOwnerTasks(current, roadmap, doneIds).map((task) => task.id)) : new Set<string>();
  const ordered = [...roadmap.ownerTasks].sort((left, right) => Number(currentBlockers.has(right.id)) - Number(currentBlockers.has(left.id)));

  return (
    <div>
      <AdminPageHeader eyebrow="Finding Alpha" title="Roadmap">
        <div className="d-flex flex-wrap gap-2" aria-label="Phase">
          {["Build", "Paper trading", "Gate", "Real money"].map((label) => (
            <span key={label} className={`badge ${label === "Build" ? "text-bg-primary" : "text-bg-light border"}`}>{label}</span>
          ))}
        </div>
      </AdminPageHeader>
      <div className="admin-kpi-row">
        <AdminKpi label="Steps" value={`${progress.done} / ${progress.total}`} hint={`${progress.percent}%`} />
        <AdminKpi label="Milestones" value={`${milestonesDone} / ${roadmap.milestones.length}`} />
        <AdminKpi label="Current" value={current ? `${current.id} ${current.title}` : "—"} />
        <AdminKpi label="Open owner tasks" value={String(openTasks.length)} />
      </div>
      <section className="card shadow-sm mb-4">
        <div className="card-body">
      <h2 className="admin-card-title">Owner tasks</h2>
      <ul className="list-unstyled mb-0">
        {ordered.map((task) => (
          <li key={task.id} className={currentBlockers.has(task.id) ? "text-warning-emphasis" : undefined}>
            <label className="d-flex flex-wrap gap-2 align-items-baseline">
              <input
                type="checkbox"
                checked={doneIds.has(task.id)}
                aria-label={task.id}
                onChange={(event) => setTask.mutate({ id: task.id, done: event.target.checked })}
              />
              <span>{task.id}</span>
              <span>{task.title}</span>
              {task.blocks.map((id) => <span key={id} className="badge text-bg-light border">{id}</span>)}
            </label>
          </li>
        ))}
      </ul>
        </div>
      </section>
      <h2 className="admin-card-title">Milestones</h2>
      {roadmap.milestones.map((milestone) => (
        <MilestoneCard key={milestone.id} milestone={milestone} doneIds={doneIds} />
      ))}
    </div>
  );
}
