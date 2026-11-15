import { describe, expect, it } from "vitest";
import {
  blockingOwnerTasks,
  currentMilestone,
  milestoneProgress,
  overallProgress,
  planUrl,
  stepStatus,
  type RoadmapFile,
} from "./roadmapModel";

const roadmap: RoadmapFile = {
  milestones: [
    {
      id: "M01",
      title: "Harness",
      plan: "docs/plans/01-agent-harness.md",
      zone: "red",
      status: "done",
      steps: [
        { id: "M01-T01", title: "One", status: "done" },
        { id: "M01-T02", title: "Two", status: "mystery" },
      ],
    },
    {
      id: "M02",
      title: "Skeleton",
      plan: "docs/plans/02-infrastructure-skeleton.md",
      zone: "red",
      status: "not_started",
      steps: [],
    },
  ],
  ownerTasks: [
    { id: "O01", title: "Create the environment", blocks: ["M02"] },
    { id: "O02", title: "Done already", blocks: ["M02"] },
  ],
};

describe("roadmapModel", () => {
  it("treats an empty milestone as no progress", () => {
    expect(milestoneProgress(roadmap.milestones[1])).toEqual({ done: 0, total: 0, percent: 0 });
  });

  it("counts only done steps and falls back an unknown status to todo", () => {
    expect(stepStatus("mystery")).toBe("todo");
    expect(milestoneProgress(roadmap.milestones[0])).toEqual({ done: 1, total: 2, percent: 50 });
    expect(overallProgress(roadmap).done).toBe(1);
  });

  it("picks the first unfinished milestone and the open tasks that block it", () => {
    expect(currentMilestone(roadmap)?.id).toBe("M02");
    const open = blockingOwnerTasks(roadmap.milestones[1], roadmap, new Set(["O02"]));
    expect(open.map((task) => task.id)).toEqual(["O01"]);
    expect(planUrl(roadmap.milestones[0])).toBe(
      "https://github.com/lx-software-ltd/findingalpha/blob/main/docs/plans/01-agent-harness.md",
    );
  });

  it("reports full progress when every step is done", () => {
    const finished: RoadmapFile = {
      milestones: [
        {
          id: "M01",
          title: "Harness",
          plan: "docs/plans/01-agent-harness.md",
          zone: "green",
          status: "done",
          steps: [{ id: "M01-T01", title: "One", status: "done" }],
        },
      ],
      ownerTasks: [],
    };
    expect(overallProgress(finished)).toEqual({ done: 1, total: 1, percent: 100 });
  });
});
