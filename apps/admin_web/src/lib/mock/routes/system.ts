import { ownerTasksFixture, runsFixture, settingsFixture, statusFixture } from "../fixtures";
import { json } from "./context";
import type { MockCtx } from "./types";

type Json = ReturnType<typeof json>;

const state: {
  tasks: { done: Record<string, { at: string }> };
  settings: typeof settingsFixture;
} = {
  tasks: structuredClone(ownerTasksFixture),
  settings: structuredClone(settingsFixture),
};

export function resetSystemMock(): void {
  state.tasks = structuredClone(ownerTasksFixture);
  state.settings = structuredClone(settingsFixture);
}

function readBody(ctx: MockCtx): Record<string, unknown> {
  if (typeof ctx.init.body !== "string") return {};
  return JSON.parse(ctx.init.body) as Record<string, unknown>;
}

export function handleSystem(ctx: MockCtx): Json | null {
  if (ctx.method === "GET" && ctx.path === "/owner-tasks") return json(200, state.tasks);
  if (ctx.method === "PUT" && ctx.path.startsWith("/owner-tasks/")) {
    const id = ctx.path.split("/").pop() ?? "";
    const body = readBody(ctx);
    if (body.done === true) state.tasks.done[id] = { at: "2026-01-03T00:00:00.000Z" };
    if (body.done === false) delete state.tasks.done[id];
    return json(200, state.tasks);
  }
  if (ctx.method === "GET" && ctx.path === "/settings") return json(200, state.settings);
  if (ctx.method === "PUT" && ctx.path === "/settings") {
    Object.assign(state.settings, readBody(ctx));
    return json(200, state.settings);
  }
  if (ctx.method === "GET" && ctx.path === "/system/status") {
    return json(200, {
      ...statusFixture,
      switches: statusFixture.switches.map((item) =>
        item.name in state.settings
          ? { ...item, setting: state.settings[item.name as keyof typeof state.settings] }
          : item,
      ),
    });
  }
  if (ctx.method === "GET" && ctx.path === "/jobs/runs") return json(200, runsFixture);
  return null;
}
