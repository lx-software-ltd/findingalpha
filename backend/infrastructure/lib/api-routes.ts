import type { HttpMethod } from "aws-cdk-lib/aws-apigatewayv2";
import { HttpMethod as Method } from "aws-cdk-lib/aws-apigatewayv2";

export interface AdminApiRoute {
  readonly path: string;
  readonly methods: HttpMethod[];
  readonly auth: "none" | "jwt" | "key";
  readonly throttle?: { readonly rate: number; readonly burst: number };
}

/** GET /health stays first. The shared integration binds under the first route. */
export const ROUTES: AdminApiRoute[] = [
  { path: "/health", methods: [Method.GET], auth: "none" },
  { path: "/me", methods: [Method.GET], auth: "jwt" },
  { path: "/owner-tasks", methods: [Method.GET], auth: "jwt" },
  { path: "/owner-tasks/{taskId}", methods: [Method.PUT], auth: "jwt" },
  { path: "/settings", methods: [Method.GET, Method.PUT], auth: "jwt" },
  { path: "/jobs/runs", methods: [Method.GET], auth: "jwt" },
  { path: "/jobs/{jobName}/run", methods: [Method.POST], auth: "jwt" },
  { path: "/universe/latest", methods: [Method.GET], auth: "jwt" },
  { path: "/system/status", methods: [Method.GET], auth: "jwt" },
  { path: "/api-keys", methods: [Method.GET], auth: "jwt" },
  { path: "/public", methods: [Method.GET], auth: "key", throttle: { rate: 2, burst: 10 } },
  { path: "/public/{proxy+}", methods: [Method.GET], auth: "key", throttle: { rate: 2, burst: 10 } },
  {
    path: "/public/{proxy+}",
    methods: [Method.PUT, Method.POST],
    auth: "key",
    throttle: { rate: 1, burst: 5 },
  },
];
