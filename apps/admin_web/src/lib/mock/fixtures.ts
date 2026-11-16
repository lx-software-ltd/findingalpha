export const ownerTasksFixture = { done: { O01: { at: "2026-01-02T00:00:00.000Z" } } };

export const settingsFixture = {
  ingestEnabled: false,
  committeeEnabled: false,
  tradingEnabled: false,
  leverageEnabled: false,
  briefEmailEnabled: false,
};

export const statusFixture = {
  switches: [
    { name: "ingestEnabled", parameter: false, setting: false, effective: false },
    { name: "committeeEnabled", parameter: false, setting: false, effective: false },
    { name: "tradingEnabled", parameter: true, setting: false, effective: false },
    { name: "leverageEnabled", parameter: false, setting: false, effective: false },
    { name: "briefEmailEnabled", parameter: false, setting: false, effective: false },
  ],
  brokerMode: "paper",
  jobs: [
    {
      job: "tick",
      schedule: "rate(15 minutes)",
      lastRun: { status: "succeeded", startedAt: "2026-01-02T00:00:00.000Z", durationMs: 120, message: "" },
    },
    {
      job: "ingest_daily",
      schedule: "0 12 ? * TUE-SAT * Asia/Hong_Kong",
      lastRun: { status: "failed", startedAt: "2026-01-01T22:00:00.000Z", durationMs: 40, message: "timeout" },
      manualRun: true,
    },
    { job: "reconcile", schedule: "30 6 ? * TUE-SAT * Asia/Hong_Kong", lastRun: null, manualRun: false },
  ],
};

export const runsFixture = {
  runs: [
    { job: "ingest_daily", status: "failed", startedAt: "2026-01-01T22:00:00.000Z", durationMs: 40, message: "timeout" },
    { job: "tick", status: "succeeded", startedAt: "2026-01-02T00:00:00.000Z", durationMs: 120, message: "" },
  ],
};
