import { afterEach, describe, expect, it, vi } from "vitest";
import { AdminApiError, adminFetch, getAdminApiErrorMessage, joinUrl } from "./apiAdminClient";
import { fromWire, toWire } from "./wireFormat";

vi.mock("./wireFormat", async () => {
  const actual = await vi.importActual<typeof import("./wireFormat")>("./wireFormat");
  return {
    ...actual,
    toWire: vi.fn(actual.toWire),
    fromWire: vi.fn(actual.fromWire),
  };
});

describe("apiAdminClient joinUrl", () => {
  it("joins base and path", () => {
    expect(joinUrl("https://api.example", "/me")).toBe("https://api.example/me");
    expect(joinUrl("https://api.example/", "me")).toBe("https://api.example/me");
  });

  it("passes through absolute URLs", () => {
    expect(joinUrl("https://x", "https://y/z")).toBe("https://y/z");
  });
});

describe("adminFetch", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.mocked(toWire).mockClear();
    vi.mocked(fromWire).mockClear();
  });

  function stubConfig(): void {
    vi.stubEnv("VITE_COGNITO_CLIENT_ID", "client");
    vi.stubEnv("VITE_COGNITO_DOMAIN", "https://auth.example.test");
    vi.stubEnv("VITE_COGNITO_REDIRECT_URI", "https://admin.example.test/callback");
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test");
    vi.stubEnv("VITE_ADMIN_MOCK", "0");
  }

  it.each([204, 205, 304])("returns status %s without building a body", async (status) => {
    stubConfig();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status, headers: { "content-type": "application/json" } })),
    );
    const response = await adminFetch("/v1/admin/settings", { requireAuth: false });
    expect(response.status).toBe(status);
    expect(await response.text()).toBe("");
  });

  it.each([204, 205, 304])("returns a non-JSON status %s without a body", async (status) => {
    stubConfig();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status, headers: { "content-type": "text/plain" } })),
    );
    const response = await adminFetch("/v1/admin/settings", { requireAuth: false });
    expect(response.status).toBe(status);
    expect(await response.text()).toBe("");
  });

  it("returns an empty JSON body", async () => {
    stubConfig();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 200, headers: { "content-type": "application/json" } })),
    );
    const response = await adminFetch("/v1/admin/settings", { requireAuth: false });
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("");
  });

  it("converts JSON with the request path", async () => {
    stubConfig();
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ portfolio_size: 12, request_id: "req-1" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const response = await adminFetch("/v1/admin/settings?pageSize=2", {
      requireAuth: false,
      method: "PUT",
      body: JSON.stringify({ portfolioSize: 12 }),
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://api.example.test/v1/admin/settings?page_size=2");
    expect(JSON.parse(String(init.body))).toEqual({ portfolio_size: 12 });
    expect(await response.json()).toEqual({ portfolioSize: 12, requestId: "req-1" });
    expect(vi.mocked(toWire).mock.calls.some((call) => call[2] === "PUT /v1/admin/settings")).toBe(true);
    expect(vi.mocked(fromWire).mock.calls.some((call) => call[2] === "PUT /v1/admin/settings")).toBe(true);
  });
});

describe("getAdminApiErrorMessage", () => {
  it("returns message from JSON body", () => {
    const err = new AdminApiError(400, '{"message":"expenseRecords[0].category must be one of: Utility"}');
    expect(getAdminApiErrorMessage(err)).toBe(
      "expenseRecords[0].category must be one of: Utility",
    );
  });

  it("returns null for non-AdminApiError", () => {
    expect(getAdminApiErrorMessage(new Error("network"))).toBeNull();
  });
});
