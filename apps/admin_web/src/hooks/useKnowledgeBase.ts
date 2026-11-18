import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminFetchJson } from "../lib/apiAdminClient";
import { queryKeys } from "../lib/queryKeys";

export type KnowledgeBaseProblem = {
  readonly key: string;
  readonly problem: string;
};

export type KnowledgeBaseStatus = {
  readonly documents: number;
  readonly bytes: number;
  readonly capBytes: number | null;
  readonly retrievals: number;
  readonly retrievalCap: number;
  readonly syncedAt: string | null;
  readonly status: string;
  readonly running: boolean;
  readonly stopping: boolean;
  readonly evaluation: {
    readonly ranAt: string | null;
    readonly questions: number;
    readonly hitAt8: number | null;
    readonly hitAt3: number | null;
  };
  readonly problems: readonly KnowledgeBaseProblem[];
  readonly failedDocuments: readonly string[];
  readonly blocked: { readonly status: string } | null;
  readonly blockedReason: string | null;
  readonly cost: { readonly storageUsd: number; readonly retrievalUsd: number; readonly totalUsd: number };
};

export type KnowledgeBaseEvaluation = {
  readonly ranAt: string | null;
  readonly questions: number;
  readonly hitAt8: number | null;
  readonly hitAt3: number | null;
  readonly results: readonly { readonly id: string; readonly rank: number | null }[];
};

export function useKnowledgeBaseStatus() {
  return useQuery({
    queryKey: queryKeys.knowledgeBase,
    queryFn: () => adminFetchJson<KnowledgeBaseStatus>("/kb/status"),
    refetchInterval: 60_000,
  });
}

export function useKnowledgeBaseEvaluation() {
  return useQuery({
    queryKey: queryKeys.knowledgeBaseEval,
    queryFn: () => adminFetchJson<KnowledgeBaseEvaluation>("/kb/eval/latest"),
    refetchInterval: 60_000,
  });
}

export function useSyncKnowledgeBase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body?: { confirmDeletion?: boolean; stop?: boolean }) =>
      adminFetchJson<{ accepted: boolean }>("/kb/sync", {
        method: "POST",
        ...(body ? { body: JSON.stringify(body) } : {}),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.knowledgeBase });
      void client.invalidateQueries({ queryKey: queryKeys.runs });
      void client.invalidateQueries({ queryKey: queryKeys.status });
    },
  });
}
