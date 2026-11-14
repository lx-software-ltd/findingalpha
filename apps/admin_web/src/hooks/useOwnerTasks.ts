import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminFetchJson } from "../lib/apiAdminClient";
import { queryKeys } from "../lib/queryKeys";

export type OwnerTaskDone = { readonly done: Record<string, { readonly at: string }> };

export function useOwnerTasks() {
  return useQuery({
    queryKey: queryKeys.ownerTasks,
    queryFn: () => adminFetchJson<OwnerTaskDone>("/owner-tasks"),
  });
}

export function useSetOwnerTask() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; done: boolean }) =>
      adminFetchJson<OwnerTaskDone>(`/owner-tasks/${input.id}`, {
        method: "PUT",
        body: JSON.stringify({ done: input.done }),
      }),
    onMutate: async (input) => {
      await client.cancelQueries({ queryKey: queryKeys.ownerTasks });
      const previous = client.getQueryData<OwnerTaskDone>(queryKeys.ownerTasks);
      client.setQueryData<OwnerTaskDone>(queryKeys.ownerTasks, (current) => {
        const done = { ...(current?.done ?? {}) };
        if (input.done) {
          done[input.id] = { at: new Date().toISOString() };
        } else {
          delete done[input.id];
        }
        return { done };
      });
      return { previous };
    },
    onError: (_error, _input, context) => {
      if (context?.previous) {
        client.setQueryData(queryKeys.ownerTasks, context.previous);
      }
    },
    onSuccess: (data) => {
      client.setQueryData(queryKeys.ownerTasks, data);
    },
  });
}
