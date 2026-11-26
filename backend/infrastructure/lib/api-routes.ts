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
  { path: "/v1/admin/me", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/owner-tasks", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/owner-tasks/{task_id}", methods: [Method.PUT], auth: "jwt" },
  { path: "/v1/admin/settings", methods: [Method.GET, Method.PUT], auth: "jwt" },
  { path: "/v1/admin/jobs/runs", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/jobs/{job_name}/run", methods: [Method.POST], auth: "jwt" },
  { path: "/v1/admin/universe/latest", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/system/status", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/api-keys", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/methodology", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/screens/latest", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/screens/{date}", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/backtests", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/backtests/{run_id}", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/kb/status", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/kb/eval/latest", methods: [Method.GET], auth: "jwt" },
  { path: "/v1/admin/kb/sync", methods: [Method.POST], auth: "jwt" },
  { path: "/v1/partner", methods: [Method.GET], auth: "key", throttle: { rate: 2, burst: 10 } },
  { path: "/v1/partner/{proxy+}", methods: [Method.GET], auth: "key", throttle: { rate: 2, burst: 10 } },
  {
    path: "/v1/partner/{proxy+}",
    methods: [Method.PUT, Method.POST],
    auth: "key",
    throttle: { rate: 1, burst: 5 },
  },
];
