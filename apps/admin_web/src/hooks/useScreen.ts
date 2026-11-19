import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { adminFetchJson } from "../lib/apiAdminClient";
import { queryKeys } from "../lib/queryKeys";

export type ScreenRow = {
  readonly rank: number;
  readonly symbol: string;
  readonly name: string;
  readonly sector: string;
  readonly composite: number | null;
  readonly groups: Readonly<Record<string, number | null>>;
  readonly factors: Readonly<Record<string, number | null>>;
  readonly z: Readonly<Record<string, number | null>>;
};

export type ScreenResponse = {
  readonly asOf: string;
  readonly registerHash: string;
  readonly counts: { readonly universe: number; readonly passed: number; readonly shortlisted: number };
  readonly rows: readonly ScreenRow[];
};

export type BacktestRun = {
  readonly runId: string;
  readonly portfolioSize: number;
  readonly registerHash: string;
};

export type SeriesMetrics = {
  readonly cagr: number | null;
  readonly volatility: number | null;
  readonly sharpe: number | null;
  readonly maxDrawdown?: { readonly drawdown: number; readonly start: string; readonly end: string };
};

export type WindowStats = {
  readonly yearly?: readonly { readonly year: string; readonly strategy: number | null; readonly benchmark: number | null }[];
  readonly averageTurnover?: number | null;
  readonly hitRate?: number | null;
  readonly costDrag?: number | null;
  readonly worstWindow?: { readonly return: number | null; readonly start: string; readonly end: string } | null;
  readonly longestBehind?: { readonly months: number; readonly start: string; readonly end: string };
};

export type BacktestDetail = {
  readonly runId: string;
  readonly portfolioSize: number;
  readonly registerHash?: string;
  readonly labels: readonly string[];
  readonly curves: {
    readonly strategy: readonly number[];
    readonly spyGross: readonly number[];
    readonly spyNet: readonly number[];
    readonly cash: readonly number[];
  };
  readonly metrics: WindowStats & {
    readonly full?: PeriodMetrics;
    readonly early?: PeriodMetrics;
    readonly holdout?: PeriodMetrics;
  };
  readonly lastPriceCount?: number;
  readonly unpricedCount?: number;
  readonly missingBenchmarkCount?: number;
};

export type PeriodMetrics = SeriesMetrics & {
  readonly benchmarks?: { readonly spyNet?: SeriesMetrics; readonly spyGross?: SeriesMetrics };
};

export function useScreen(date: string) {
  const path = date ? `/screens/${date}` : "/screens/latest";
  return useQuery({
    queryKey: date ? queryKeys.screen(date) : queryKeys.screenLatest,
    queryFn: () => adminFetchJson<ScreenResponse>(path),
  });
}

export function useBacktests() {
  return useQuery({
    queryKey: queryKeys.backtests,
    queryFn: () => adminFetchJson<{ runs: readonly BacktestRun[] }>("/backtests"),
  });
}

export function useBacktest(runId: string) {
  return useQuery({
    queryKey: queryKeys.backtest(runId),
    queryFn: () => adminFetchJson<BacktestDetail>(`/backtests/${runId}`),
    enabled: runId.length > 0,
    placeholderData: keepPreviousData,
  });
}
