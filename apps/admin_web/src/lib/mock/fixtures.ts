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
    { job: "backtest", schedule: "", lastRun: null, manualRun: true },
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

export const screenFixture = {
  asOf: "2017-02-28",
  registerHash: "abc123abc123abcd",
  counts: { universe: 30, passed: 26, shortlisted: 2 },
  rows: [
    {
      rank: 1,
      symbol: "AAA",
      name: "Aaa Example",
      sector: "tech",
      composite: 1.2,
      groups: { quality: 0.4, value: 0.3, trend: 0.5 },
      factors: { roic: 0.2 },
      z: { roic: 1.1 },
    },
    {
      rank: 2,
      symbol: "BBB",
      name: "Bbb Example",
      sector: "health",
      composite: 0.4,
      groups: { quality: 0.1, value: 0.2, trend: 0.1 },
      factors: { roic: 0.05 },
      z: { roic: 0.2 },
    },
  ],
};

export const backtestListFixture = [
  { runId: "run-example", portfolioSize: 20, registerHash: "abc123abc123abcd", createdAt: "2017-04-01T00:00:00Z" },
];

export const backtestFixture = {
  runId: "run-example",
  portfolioSize: 20,
  registerHash: "abc123abc123abcd",
  labels: ["start", "2017-02", "2017-03"],
  curves: {
    strategy: [100, 108.3, 117.5],
    spyGross: [100, 101, 102],
    spyNet: [100, 100.7, 101.4],
    cash: [100, 100.1, 100.2],
  },
  lastPriceCount: 0,
  unpricedCount: 0,
  missingBenchmarkCount: 0,
  metrics: {
    full: {
      cagr: 0.08,
      volatility: 0.12,
      sharpe: 0.5,
      maxDrawdown: { drawdown: -0.1, start: "2017-02", end: "2017-03" },
      benchmarks: {
        spyNet: { cagr: 0.04, volatility: 0.1, sharpe: 0.3, maxDrawdown: { drawdown: -0.2, start: "2017-02", end: "2017-03" } },
        spyGross: { cagr: 0.05, volatility: 0.1, sharpe: 0.4, maxDrawdown: { drawdown: -0.18, start: "2017-02", end: "2017-03" } },
      },
    },
    early: { cagr: 0.08, volatility: 0.12, sharpe: 0.5, maxDrawdown: { drawdown: -0.1, start: "2017-02", end: "2017-03" } },
    holdout: { cagr: null, volatility: null, sharpe: null, maxDrawdown: { drawdown: 0, start: "start", end: "start" } },
    hitRate: 0.5,
    averageTurnover: 0.2,
    costDrag: 0.01,
    worstWindow: { return: -0.08, start: "2017-02", end: "2018-01" },
    longestBehind: { months: 3, start: "2017-02", end: "2017-04" },
    yearly: [{ year: "2017", strategy: 0.175, benchmark: 0.014 }],
  },
};

export const runsFixture = {
  runs: [
    { job: "ingest_daily", status: "failed", startedAt: "2026-01-01T22:00:00.000Z", durationMs: 40, message: "timeout" },
    { job: "tick", status: "succeeded", startedAt: "2026-01-02T00:00:00.000Z", durationMs: 120, message: "" },
  ],
};
