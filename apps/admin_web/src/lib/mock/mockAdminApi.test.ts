import { beforeEach, describe, expect, it } from "vitest";
import { mockAdminFetch } from "./mockAdminApi";
import { resetSystemMock } from "./routes/system";

describe("mock admin api", () => {
  beforeEach(() => {
    resetSystemMock();
  });

  it("returns the fixtures", async () => {
    const tasks = await (await mockAdminFetch("/v1/admin/owner-tasks")).json();
    expect(tasks.done.O01.at).toBe("2026-01-02T00:00:00.000Z");
    const keys = await (await mockAdminFetch("/v1/admin/api-keys")).json();
    expect(keys.keys.map((row: { label: string }) => row.label)).toContain("monitor");
    expect(JSON.stringify(keys)).not.toContain("APIKEY#");
    const status = await (await mockAdminFetch("/v1/admin/system/status")).json();
    expect(status.jobs.map((job: { job: string }) => job.job)).toContain("tick");
    expect(status.jobs.some((job: { lastRun: unknown }) => job.lastRun === null)).toBe(true);
    const methodology = await (await mockAdminFetch("/v1/admin/methodology")).json();
    expect(methodology.register.factors[0].status).toBe("owner_accepted");
    expect(methodology.counts.ownerAccepted).toBe(4);
    const screen = await (await mockAdminFetch("/v1/admin/screens/latest")).json();
    expect(screen.rows[0].symbol).toBe("AAA");
    const backtests = await (await mockAdminFetch("/v1/admin/backtests")).json();
    expect(backtests.runs[0].runId).toBe("run-example");
    const knowledge = await (await mockAdminFetch("/v1/admin/kb/status")).json();
    expect(knowledge.documents).toBe(131);
    const evaluation = await (await mockAdminFetch("/v1/admin/kb/eval/latest")).json();
    expect(evaluation.results[0].id).toBe("q01");
    const universe = await (await mockAdminFetch("/v1/admin/universe/latest")).json();
    expect(universe.asOf).toBe("2024-06-03");
    expect(universe.backfill.prices.cursor).toBe(2);
    const run = await mockAdminFetch("/v1/admin/jobs/ingest_daily/run", { method: "POST" });
    expect(run.status).toBe(202);
    const refused = await mockAdminFetch("/v1/admin/jobs/ingest_daily/run", {
      method: "POST",
      body: JSON.stringify({ day: "2026-11-16" }),
    });
    expect(refused.status).toBe(400);
    const sized = await mockAdminFetch("/v1/admin/jobs/backtest/run", {
      method: "POST",
      body: JSON.stringify({ portfolioSize: 15 }),
    });
    expect(sized.status).toBe(202);
    expect((await sized.json()).portfolioSize).toBe(15);
    const sync = await mockAdminFetch("/v1/admin/jobs/kb_sync_check/run", {
      method: "POST",
      body: JSON.stringify({ confirmDeletion: true }),
    });
    expect(sync.status).toBe(202);
    const stopped = await mockAdminFetch("/v1/admin/jobs/kb_sync_check/run", {
      method: "POST",
      body: JSON.stringify({ stop: true }),
    });
    expect(stopped.status).toBe(202);
    const badSync = await mockAdminFetch("/v1/admin/jobs/kb_sync_check/run", {
      method: "POST",
      body: JSON.stringify({ confirmDeletion: false }),
    });
    expect(badSync.status).toBe(400);
  });

  it("keeps a PUT in memory", async () => {
    await mockAdminFetch("/v1/admin/settings", { method: "PUT", body: JSON.stringify({ ingestEnabled: true }) });
    const settings = await (await mockAdminFetch("/v1/admin/settings")).json();
    expect(settings.ingestEnabled).toBe(true);
    await mockAdminFetch("/v1/admin/owner-tasks/O04", { method: "PUT", body: JSON.stringify({ done: true }) });
    const tasks = await (await mockAdminFetch("/v1/admin/owner-tasks")).json();
    expect(tasks.done.O04).toBeDefined();
  });
});
