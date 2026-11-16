import {
  backtestFixture,
  backtestListFixture,
  methodologyFixture,
  ownerTasksFixture,
  runsFixture,
  screenFixture,
  settingsFixture,
  statusFixture,
} from "../fixtures";
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
  if (ctx.method === "GET" && ctx.path === "/api-keys") {
    const soon = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
    return json(200, {
      writesEnabled: false,
      keys: [
        {
          keyId: "active1",
          label: "monitor",
          tier: "admin",
          scopes: ["system"],
          allowWrite: false,
          revoked: false,
          createdAt: "2026-01-01T00:00:00.000Z",
          expiresAt: "2027-01-01T00:00:00.000Z",
          lastUsedAt: null,
        },
        {
          keyId: "soon1",
          label: "rotation",
          tier: "admin",
          scopes: ["system", "operate"],
          allowWrite: true,
          revoked: false,
          createdAt: "2026-01-01T00:00:00.000Z",
          expiresAt: soon,
          lastUsedAt: null,
        },
        {
          keyId: "revoked1",
          label: "old",
          tier: "admin",
          scopes: ["research"],
          allowWrite: false,
          revoked: true,
          createdAt: "2025-01-01T00:00:00.000Z",
          expiresAt: null,
          lastUsedAt: null,
        },
      ],
    });
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
  if (ctx.method === "GET" && ctx.path === "/methodology") return json(200, methodologyFixture);
  if (ctx.method === "GET" && (ctx.path === "/screens/latest" || ctx.path === "/screens/2017-02-28")) {
    return json(200, screenFixture);
  }
  if (ctx.method === "GET" && ctx.path.startsWith("/screens/")) return json(404, { message: "Not found" });
  if (ctx.method === "GET" && ctx.path === "/backtests") return json(200, { runs: backtestListFixture });
  if (ctx.method === "GET" && ctx.path === "/backtests/run-example") return json(200, backtestFixture);
  if (ctx.method === "GET" && ctx.path.startsWith("/backtests/")) return json(404, { message: "Not found" });
  if (ctx.method === "GET" && ctx.path === "/universe/latest") {
    return json(200, {
      asOf: "2024-06-03",
      members: 4,
      counts: { assets: 13, price: 11, marketCap: 4 },
      coverage: { flows: { revenue: 0.5 }, stocks: { totalAssets: 0.5 } },
      lastPriceDate: "2024-06-03",
      backfill: {
        prices: { status: "running", cursor: 2, total: 8 },
        fundamentals: null,
      },
    });
  }
  if (ctx.method === "POST" && /^\/jobs\/[^/]+\/run$/.test(ctx.path)) return json(202, { accepted: true });
  return null;
}
