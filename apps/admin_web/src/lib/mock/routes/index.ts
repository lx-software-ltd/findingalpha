import { handleSystem } from "./system";
import type { MockRoute } from "./types";

export const mockRoutes: readonly MockRoute[] = [
  { pattern: /^\/(owner-tasks|settings|system\/status|jobs\/runs|api-keys)/, handler: handleSystem },
];
