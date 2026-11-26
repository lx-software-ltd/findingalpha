import { useQuery } from "@tanstack/react-query";
import { adminFetchJson } from "../lib/apiAdminClient";
import { queryKeys } from "../lib/queryKeys";

export type MethodologyCitation = {
  readonly document?: string;
  readonly locator?: string;
  readonly quote?: string;
} | null;

export type MethodologyFactor = {
  readonly id: string;
  readonly name: string;
  readonly group: string;
  readonly direction: string;
  readonly formula: string;
  readonly parameters: Readonly<Record<string, number>>;
  readonly status: string;
  readonly acceptedNote?: string;
  readonly citation: MethodologyCitation;
};

export type MethodologyResponse = {
  readonly hash: string;
  readonly counts: {
    readonly entries: number;
    readonly provisional: number;
    readonly cited: number;
    readonly ownerAccepted: number;
  };
  readonly register: {
    readonly factors: readonly MethodologyFactor[];
    readonly composite: {
      readonly status: string;
      readonly groupWeights: Readonly<Record<string, number>>;
      readonly winsoriseStdDevs: number;
      readonly minSectorSize: number;
      readonly minFactorsPerGroupShare: number;
      readonly standardise: string;
      readonly acceptedNote?: string;
      readonly citation?: MethodologyCitation;
    };
    readonly screen: {
      readonly status: string;
      readonly shortlistSize: number;
      readonly hardFilters: readonly { readonly id: string; readonly field: string; readonly op: string; readonly value: number }[];
      readonly acceptedNote?: string;
    };
  };
};

export function useMethodology() {
  return useQuery({
    queryKey: queryKeys.methodology,
    queryFn: () => adminFetchJson<MethodologyResponse>("/v1/admin/methodology"),
  });
}
