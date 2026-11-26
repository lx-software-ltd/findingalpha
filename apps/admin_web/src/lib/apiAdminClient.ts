import { ensureFreshTokens } from "./auth";
import { getAdminConfig } from "./config";
import { wireFormat } from "./contracts/generated";
import { excluded, fromWire, toWire, type WireContract } from "./wireFormat";

const CONTRACT = wireFormat as unknown as WireContract;

export class AdminApiError extends Error {
  readonly status: number;
  readonly responseBody: string;

  constructor(status: number, responseBody: string) {
    super(`Admin API request failed (${status})`);
    this.name = "AdminApiError";
    this.status = status;
    this.responseBody = responseBody;
  }
}

/** Parses API Gateway/Lambda JSON error bodies like `{ "message": "…" }`. */
export function getAdminApiErrorMessage(err: unknown): string | null {
  if (!(err instanceof AdminApiError)) return null;
  try {
    const parsed = JSON.parse(err.responseBody) as { message?: unknown };
    if (typeof parsed.message === "string" && parsed.message.trim()) {
      return parsed.message.trim();
    }
  } catch {
    /* ignore malformed JSON */
  }
  return null;
}

/** Join API base URL and path (exported for unit tests). */
export function joinUrl(base: string, path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const prefix = base.endsWith("/") ? base.slice(0, -1) : base;
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${prefix}${suffix}`;
}

export type AdminFetchOptions = RequestInit & {
  /**
   * When false, do not attach Authorization (for public routes like GET /health).
   * Default true: always send the Cognito **ID token** (see HttpJwtAuthorizer
   * jwtAudience in CDK — ID token `aud` matches the app client; access tokens
   * do not).
   */
  readonly requireAuth?: boolean;
};

export async function adminFetch(
  path: string,
  init: AdminFetchOptions = {}
): Promise<Response> {
  const { requireAuth = true, ...rest } = init;
  // The comparison is on `import.meta.env` so Vite can drop the mock chunk when the flag is "0".
  if (import.meta.env.VITE_ADMIN_MOCK === "1") {
    const { mockAdminFetch } = await import("./mock/mockAdminApi");
    const res = await mockAdminFetch(path, rest);
    if (!res.ok) {
      throw new AdminApiError(res.status, await res.text());
    }
    return res;
  }
  const cfg = getAdminConfig();
  if (!cfg.apiBaseUrl) {
    throw new Error("VITE_API_BASE_URL is not set");
  }
  const headers = new Headers(rest.headers);
  if (requireAuth) {
    const idToken = await ensureFreshTokens();
    headers.set("Authorization", `Bearer ${idToken}`);
  }
  const barePath = path.split("?")[0] ?? path;
  const method = (rest.method || "GET").toUpperCase();
  // rootMaps keys are "METHOD /path". The codec still looks up that string.
  const route = `${method} ${barePath}`;
  const skip = excluded(barePath, CONTRACT);
  const wirePath = skip ? path : convertQuery(path);
  let body = rest.body;
  if (!skip && typeof body === "string" && body) {
    try {
      body = JSON.stringify(toWire(JSON.parse(body), CONTRACT, route));
    } catch {
      // A body that is not JSON is sent unchanged.
    }
  }
  const url = joinUrl(cfg.apiBaseUrl, wirePath);
  if (!headers.has("Content-Type") && body) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(url, { ...rest, body, headers });
  // new Response rejects a body on 204, 205, and 304, including a non-JSON body.
  if (res.status === 204 || res.status === 205 || res.status === 304) {
    return new Response(null, {
      status: res.status,
      statusText: res.statusText,
      headers: res.headers,
    });
  }
  const type = res.headers.get("content-type") ?? "";
  if (!skip && type.toLowerCase().includes("json")) {
    const text = await res.text();
    let converted = text;
    try {
      converted = JSON.stringify(fromWire(JSON.parse(text), CONTRACT, route));
    } catch {
      converted = text;
    }
    if (!res.ok) {
      throw new AdminApiError(res.status, converted);
    }
    return new Response(responseBody(res.status, converted), {
      status: res.status,
      statusText: res.statusText,
      headers: res.headers,
    });
  }
  if (!res.ok) {
    const text = await res.text();
    throw new AdminApiError(res.status, text);
  }
  return res;
}

function responseBody(status: number, text: string): string | null {
  if (status === 204 || status === 205 || status === 304 || text.length === 0) {
    return null;
  }
  return text;
}

function convertQuery(path: string): string {
  const mark = path.indexOf("?");
  if (mark < 0) {
    return path;
  }
  const params = new URLSearchParams(path.slice(mark + 1));
  const next = new URLSearchParams();
  for (const [key, value] of params) {
    const renamed = Object.keys(toWire({ [key]: null }, CONTRACT) as Record<string, unknown>)[0] ?? key;
    next.append(renamed, value);
  }
  return `${path.slice(0, mark + 1)}${next.toString()}`;
}

export async function adminFetchJson<T>(
  path: string,
  init: AdminFetchOptions = {}
): Promise<T> {
  const res = await adminFetch(path, init);
  return (await res.json()) as T;
}
