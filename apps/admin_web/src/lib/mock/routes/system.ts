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
import { methodology } from "../../contracts/generated";
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

function runJob(ctx: MockCtx): Json {
  const job = ctx.path.split("/")[2] ?? "";
  const raw = ctx.init.body;
  let record: Record<string, unknown> = {};
  if (typeof raw === "string" && raw.trim()) {
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return json(400, { message: "body must be a JSON object" });
      }
      record = parsed as Record<string, unknown>;
    } catch {
      return json(400, { message: "body must be a JSON object" });
    }
  }
  if (Object.keys(record).length === 0) return json(202, { accepted: true });
  if (job === "kb_sync_check") {
    const keys = Object.keys(record);
    if (keys.length === 1 && (record.confirmDeletion === true || record.stop === true)) {
      return json(202, { accepted: true });
    }
    return json(400, { message: "only confirmDeletion true or stop true is allowed" });
  }
  if (job !== "backtest") return json(400, { message: "this job does not take a body" });
  if (Object.keys(record).some((key) => key !== "portfolioSize")) {
    return json(400, { message: "only portfolioSize is allowed" });
  }
  const size = record.portfolioSize;
  const { portfolioSizeMin, portfolioSizeMax } = methodology.backtest;
  if (typeof size !== "number" || !Number.isInteger(size) || size < portfolioSizeMin || size > portfolioSizeMax) {
    return json(400, { message: `portfolioSize must be an integer from ${portfolioSizeMin} to ${portfolioSizeMax}` });
  }
  return json(202, { accepted: true, portfolioSize: size });
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
  if (ctx.method === "GET" && (ctx.path === "/backtests/run-example" || ctx.path === "/backtests/run-other")) {
    const runId = ctx.path.slice("/backtests/".length);
    return json(200, { ...backtestFixture, runId });
  }
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
  if (ctx.method === "POST" && /^\/jobs\/[^/]+\/run$/.test(ctx.path)) return runJob(ctx);
  return null;
}
