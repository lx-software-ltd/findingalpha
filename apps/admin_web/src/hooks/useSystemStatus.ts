import { useQuery } from "@tanstack/react-query";
import { adminFetchJson } from "../lib/apiAdminClient";
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
    readonly lastRun: JobRun | null;
  }[];
};

export function useSystemStatus() {
  return useQuery({
    queryKey: queryKeys.status,
    queryFn: () => adminFetchJson<SystemStatus>("/system/status"),
    refetchInterval: 60_000,
  });
}

export function useJobRuns() {
  return useQuery({
    queryKey: queryKeys.runs,
    queryFn: () => adminFetchJson<{ runs: JobRun[] }>("/jobs/runs?limit=50"),
    refetchInterval: 60_000,
  });
}
