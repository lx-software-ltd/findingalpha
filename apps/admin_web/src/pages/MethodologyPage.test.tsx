import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
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
    expect(screen.getAllByText("NOPAT_ttm / average(investedCapital)").length).toBeGreaterThan(0);
    expect(screen.getByText(/Register hash abc123abc123abcd/)).toHaveClass("small");
    expect(screen.queryByText("Register hash", { selector: ".admin-kpi-label" })).toBeNull();
    expect(screen.getAllByText("provisional").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("row", { name: /Return on invested capital/ }));
    expect(document.querySelector(".admin-expand.is-open")).toHaveTextContent("maxTaxRate 0.35");
    expect(document.querySelector(".admin-expand.is-open")).toHaveTextContent("higher");
    expect(screen.getByText(/quality 0.4/)).toBeInTheDocument();
    expect(screen.getByText("netDebtToEbitda <= 4")).toBeInTheDocument();
  });
});
