export type ApiKeyRow = {
  readonly keyId: string;
  readonly label: string;
  readonly tier: string;
  readonly scopes: readonly string[];
  readonly allowWrite: boolean;
  readonly revoked: boolean;
  readonly createdAt: string;
  readonly expiresAt: string | null;
  readonly lastUsedAt: string | null;
};

const SOON_MS = 14 * 24 * 60 * 60 * 1000;

export function apiKeyState(row: Pick<ApiKeyRow, "revoked" | "expiresAt">, now: number): "active" | "expired" | "revoked" {
  if (row.revoked) return "revoked";
  if (row.expiresAt && Date.parse(row.expiresAt) <= now) return "expired";
  return "active";
}

export function expiresSoon(row: Pick<ApiKeyRow, "revoked" | "expiresAt">, now: number): boolean {
  if (apiKeyState(row, now) !== "active" || !row.expiresAt) return false;
  const remaining = Date.parse(row.expiresAt) - now;
  return remaining <= SOON_MS;
}
