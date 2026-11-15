export const GLOBAL_DEFAULT_CURRENCY = "USD";
export const SUPPORTED_CURRENCIES = ["USD"] as const;
export type CurrencyCode = (typeof SUPPORTED_CURRENCIES)[number];

const SUPPORTED_SET = new Set<string>(SUPPORTED_CURRENCIES);

export function isSupportedCurrency(code: string): boolean {
  return SUPPORTED_SET.has(code.trim().toUpperCase());
}

export function coerceSupportedCurrency(raw: string, fallback: CurrencyCode): CurrencyCode {
  const code = raw.trim().toUpperCase();
  return isSupportedCurrency(code) ? (code as CurrencyCode) : fallback;
}
