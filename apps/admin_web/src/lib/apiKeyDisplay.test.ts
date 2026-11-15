import { describe, expect, it } from "vitest";
import { apiKeyState, expiresSoon } from "./apiKeyDisplay";

const now = Date.parse("2026-06-15T00:00:00.000Z");

describe("api key display", () => {
  it("names revoked, expired, and active keys", () => {
    expect(apiKeyState({ revoked: true, expiresAt: "2026-07-01T00:00:00.000Z" }, now)).toBe("revoked");
    expect(apiKeyState({ revoked: false, expiresAt: "2026-06-01T00:00:00.000Z" }, now)).toBe("expired");
    expect(apiKeyState({ revoked: false, expiresAt: null }, now)).toBe("active");
  });

  it("highlights a key that expires within 14 days", () => {
    expect(expiresSoon({ revoked: false, expiresAt: "2026-06-20T00:00:00.000Z" }, now)).toBe(true);
    expect(expiresSoon({ revoked: false, expiresAt: "2026-08-01T00:00:00.000Z" }, now)).toBe(false);
    expect(expiresSoon({ revoked: true, expiresAt: "2026-06-20T00:00:00.000Z" }, now)).toBe(false);
    expect(expiresSoon({ revoked: false, expiresAt: "2026-06-01T00:00:00.000Z" }, now)).toBe(false);
  });
});
