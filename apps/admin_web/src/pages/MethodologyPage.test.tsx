import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MethodologyPage } from "./MethodologyPage";

const fetchJson = vi.fn();

vi.mock("../lib/apiAdminClient", () => ({
  adminFetchJson: (...args: unknown[]) => fetchJson(...args),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MethodologyPage />
    </QueryClientProvider>,
  );
}

describe("MethodologyPage", () => {
  beforeEach(() => {
    fetchJson.mockReset();
    fetchJson.mockResolvedValue({
      hash: "abc123abc123abcd",
      counts: { entries: 3, provisional: 3, cited: 0 },
      register: {
        factors: [
          {
            id: "roic",
            name: "Return on invested capital",
            group: "quality",
            direction: "higher",
            formula: "NOPAT_ttm / average(investedCapital)",
            parameters: { maxTaxRate: 0.35, defaultTaxRate: 0.21 },
            status: "provisional",
            citation: null,
          },
        ],
        composite: {
          status: "provisional",
          groupWeights: { quality: 0.4, value: 0.3, trend: 0.3 },
          winsorisePercentiles: [2.5, 97.5],
          minSectorSize: 10,
          minFactorsPerGroupShare: 0.5,
          standardise: "zscore_within_sector",
        },
        screen: {
          status: "provisional",
          shortlistSize: 60,
          hardFilters: [{ id: "debtCeiling", field: "netDebtToEbitda", op: "<=", value: 4 }],
        },
      },
    });
  });

  it("shows the provisional register", async () => {
    renderPage();
    expect(await screen.findByText("Return on invested capital")).toBeInTheDocument();
    expect(screen.getByText("NOPAT_ttm / average(investedCapital)")).toBeInTheDocument();
    expect(screen.getByText("abc123abc123abcd")).toBeInTheDocument();
    expect(screen.getAllByText("provisional").length).toBeGreaterThan(0);
    expect(screen.getByText(/quality 0.4/)).toBeInTheDocument();
    expect(screen.getByText("netDebtToEbitda <= 4")).toBeInTheDocument();
  });
});
