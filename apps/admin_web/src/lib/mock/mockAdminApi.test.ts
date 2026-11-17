import { beforeEach, describe, expect, it } from "vitest";
import { mockAdminFetch } from "./mockAdminApi";
import { resetSystemMock } from "./routes/system";

describe("mock admin api", () => {
  beforeEach(() => {
    resetSystemMock();
  });

  it("returns the fixtures", async () => {
    const tasks = await (await mockAdminFetch("/owner-tasks")).json();
    expect(tasks.done.O01.at).toBe("2026-01-02T00:00:00.000Z");
    const keys = await (await mockAdminFetch("/api-keys")).json();
    expect(keys.keys.map((row: { label: string }) => row.label)).toContain("monitor");
    expect(JSON.stringify(keys)).not.toContain("APIKEY#");
    const status = await (await mockAdminFetch("/system/status")).json();
    expect(status.jobs.map((job: { job: string }) => job.job)).toContain("tick");
    expect(status.jobs.some((job: { lastRun: unknown }) => job.lastRun === null)).toBe(true);
    const methodology = await (await mockAdminFetch("/methodology")).json();
    expect(methodology.register.factors[0].status).toBe("provisional");
    const screen = await (await mockAdminFetch("/screens/latest")).json();
    expect(screen.rows[0].symbol).toBe("AAA");
    const backtests = await (await mockAdminFetch("/backtests")).json();
    expect(backtests.runs[0].runId).toBe("run-example");
    const universe = await (await mockAdminFetch("/universe/latest")).json();
    expect(universe.asOf).toBe("2024-06-03");
    expect(universe.backfill.prices.cursor).toBe(2);
    const run = await mockAdminFetch("/jobs/ingest_daily/run", { method: "POST" });
    expect(run.status).toBe(202);
    const refused = await mockAdminFetch("/jobs/ingest_daily/run", {
      method: "POST",
      body: JSON.stringify({ day: "2026-11-16" }),
    });
    expect(refused.status).toBe(400);
    const sized = await mockAdminFetch("/jobs/backtest/run", {
      method: "POST",
      body: JSON.stringify({ portfolioSize: 15 }),
    });
    expect(sized.status).toBe(202);
    expect((await sized.json()).portfolioSize).toBe(15);
  });

  it("keeps a PUT in memory", async () => {
    await mockAdminFetch("/settings", { method: "PUT", body: JSON.stringify({ ingestEnabled: true }) });
    const settings = await (await mockAdminFetch("/settings")).json();
    expect(settings.ingestEnabled).toBe(true);
    await mockAdminFetch("/owner-tasks/O04", { method: "PUT", body: JSON.stringify({ done: true }) });
    const tasks = await (await mockAdminFetch("/owner-tasks")).json();
    expect(tasks.done.O04).toBeDefined();
  });
});
