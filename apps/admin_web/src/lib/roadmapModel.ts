const STEP_STATUSES = new Set(["todo", "doing", "done"]);

export type RoadmapStep = {
  readonly id: string;
  readonly title: string;
  readonly status: string;
};

export type RoadmapMilestone = {
  readonly id: string;
  readonly title: string;
  readonly plan: string;
  readonly zone: string;
  readonly status: string;
  readonly pullRequests?: readonly string[];
  readonly steps: readonly RoadmapStep[];
};

export type RoadmapOwnerTask = {
  readonly id: string;
  readonly title: string;
  readonly blocks: readonly string[];
};

export type RoadmapFile = {
  readonly milestones: readonly RoadmapMilestone[];
  readonly ownerTasks: readonly RoadmapOwnerTask[];
};

export type Progress = { readonly done: number; readonly total: number; readonly percent: number };

export function stepStatus(status: string): string {
  return STEP_STATUSES.has(status) ? status : "todo";
}

export function milestoneProgress(milestone: RoadmapMilestone): Progress {
  const total = milestone.steps.length;
  const done = milestone.steps.filter((step) => stepStatus(step.status) === "done").length;
  return { done, total, percent: total === 0 ? 0 : Math.round((done / total) * 100) };
}

export function overallProgress(roadmap: RoadmapFile): Progress {
  const steps = roadmap.milestones.flatMap((milestone) => milestone.steps);
  return milestoneProgress({ id: "", title: "", plan: "", zone: "", status: "", steps });
}

export function currentMilestone(roadmap: RoadmapFile): RoadmapMilestone | undefined {
  return (
    roadmap.milestones.find((milestone) => milestone.status === "in_progress") ??
    roadmap.milestones.find((milestone) => milestone.status === "not_started")
  );
}

export function blockingOwnerTasks(
  milestone: RoadmapMilestone,
  roadmap: RoadmapFile,
  doneIds: ReadonlySet<string>,
): RoadmapOwnerTask[] {
  return roadmap.ownerTasks.filter(
    (task) => task.blocks.includes(milestone.id) && !doneIds.has(task.id),
  );
}

export function planUrl(milestone: RoadmapMilestone): string {
  return `https://github.com/lx-software-ltd/findingalpha/blob/main/${milestone.plan}`;
}
