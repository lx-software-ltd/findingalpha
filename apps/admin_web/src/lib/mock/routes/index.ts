import { handleSystem } from "./system";
import type { MockRoute } from "./types";

export const mockRoutes: readonly MockRoute[] = [
  { pattern: /^\/(owner-tasks|settings|system\/status|jobs\/runs|jobs\/[^/]+\/run|universe\/latest|api-keys|methodology|screens\/latest|screens\/[^/]+|backtests$|backtests\/[^/]+)/, handler: handleSystem },
];
