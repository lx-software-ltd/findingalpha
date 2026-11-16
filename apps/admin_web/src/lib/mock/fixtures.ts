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
      job: "backfill_prices",
      schedule: "",
      lastRun: {
        status: "partial",
        startedAt: "2026-01-01T22:00:00.000Z",
        durationMs: 40,
        message: "9 of 131, continues on the next tick",
      },
      progress: { status: "running", cursor: 9, total: 131 },
      manualRun: true,
    },
    {
      job: "ingest_daily",
      schedule: "0 12 ? * TUE-SAT * Asia/Hong_Kong",
      lastRun: { status: "failed", startedAt: "2026-01-01T22:00:00.000Z", durationMs: 40, message: "timeout" },
      manualRun: true,
    },
    { job: "reconcile", schedule: "30 12 ? * TUE-SAT * Asia/Hong_Kong", lastRun: null, manualRun: false },
  ],
};

export const methodologyFixture = {
  hash: "abc123abc123abcd",
  counts: { entries: 3, provisional: 3, cited: 0 },
  register: {
    factors: [
      {
        id: "roic",
        name: "Return on invested capital",
        group: "quality",
        direction: "higher",
        formula: "NOPAT_ttm / average(investedCapital)",
        parameters: { maxTaxRate: 0.35, defaultTaxRate: 0.21 },
        status: "provisional",
        citation: null,
      },
    ],
    composite: {
      status: "provisional",
      groupWeights: { quality: 0.4, value: 0.3, trend: 0.3 },
      winsorisePercentiles: [2.5, 97.5],
      minSectorSize: 10,
      minFactorsPerGroupShare: 0.5,
      standardise: "zscore_within_sector",
    },
    screen: {
      status: "provisional",
      shortlistSize: 60,
      hardFilters: [{ id: "debtCeiling", field: "netDebtToEbitda", op: "<=", value: 4 }],
    },
  },
};

export const runsFixture = {
  runs: [
    { job: "ingest_daily", status: "failed", startedAt: "2026-01-01T22:00:00.000Z", durationMs: 40, message: "timeout" },
    { job: "tick", status: "succeeded", startedAt: "2026-01-02T00:00:00.000Z", durationMs: 120, message: "" },
  ],
};
