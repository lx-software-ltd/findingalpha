import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminFetchJson } from "../lib/apiAdminClient";
import { apiKeyState, expiresSoon, type ApiKeyRow } from "../lib/apiKeyDisplay";
import { queryKeys } from "../lib/queryKeys";

export type JobRun = {
  readonly job?: string;
  readonly status: string;
  readonly startedAt: string;
  readonly durationMs: number;
  readonly message: string;
};

export type SystemStatus = {
  readonly switches: readonly {
    readonly name: string;
    readonly parameter: boolean;
    readonly setting: boolean;
    readonly effective: boolean;
  }[];
  readonly brokerMode: string;
  readonly jobs: readonly {
    readonly job: string;
    readonly schedule: string;
    readonly manualRun?: boolean;
    readonly keyRun?: boolean;
    readonly progress?: { readonly status?: string; readonly cursor: number; readonly total: number } | null;
    readonly lastRun: JobRun | null;
  }[];
};

export type UniverseLatest = {
  readonly asOf: string | null;
  readonly members: number;
  readonly counts: Readonly<Record<string, number>>;
  readonly coverage?: {
    readonly flows?: Readonly<Record<string, number | null>>;
    readonly stocks?: Readonly<Record<string, number | null>>;
    readonly shareFlows?: Readonly<Record<string, number | null>>;
  };
  readonly lastPriceDate: string | null;
  readonly backfill?: {
    readonly prices: { readonly status?: string; readonly cursor: number; readonly total: number } | null;
    readonly fundamentals: { readonly status?: string; readonly cursor: number; readonly total: number } | null;
  };
};

export function useSystemStatus() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: () => adminFetchJson<SystemStatus>("/system/status"),
    refetchInterval: 60_000,
  });
}

export function useApiKeys() {
  return useQuery({
    queryKey: queryKeys.apiKeys,
    queryFn: async () => {
      const data = await adminFetchJson<{ keys: ApiKeyRow[]; writesEnabled?: boolean }>("/api-keys");
      const now = Date.now();
      return {
        writesEnabled: data.writesEnabled === true,
        keys: data.keys.map((row) => ({
          ...row,
          state: apiKeyState(row, now),
          soon: expiresSoon(row, now),
        })),
      };
    },
    refetchInterval: 60_000,
  });
}

export function useUniverse() {
  return useQuery({
    queryKey: queryKeys.universe,
    queryFn: () => adminFetchJson<UniverseLatest>("/universe/latest"),
    refetchInterval: 60_000,
  });
}

export function useRunJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (job: string) =>
      adminFetchJson<{ accepted: boolean }>(`/jobs/${job}/run`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.runs });
      void client.invalidateQueries({ queryKey: queryKeys.status });
    },
  });
}

export function useJobRuns() {
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: () => adminFetchJson<{ runs: JobRun[] }>("/jobs/runs?limit=50"),
    refetchInterval: 60_000,
  });
}
