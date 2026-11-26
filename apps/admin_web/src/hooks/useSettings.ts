import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminFetchJson } from "../lib/apiAdminClient";
import { queryKeys } from "../lib/queryKeys";

export type Settings = {
  readonly ingestEnabled: boolean;
  readonly committeeEnabled: boolean;
  readonly tradingEnabled: boolean;
  readonly leverageEnabled: boolean;
  readonly briefEmailEnabled: boolean;
};

export function useSettings() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: () => adminFetchJson<Settings>("/v1/admin/settings"),
  });
}

export function usePutSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Settings>) =>
      adminFetchJson<Settings>("/v1/admin/settings", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: (data) => {
      client.setQueryData(queryKeys.settings, data);
      void client.invalidateQueries({ queryKey: queryKeys.status });
    },
  });
}
