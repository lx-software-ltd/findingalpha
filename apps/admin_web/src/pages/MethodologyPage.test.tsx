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
      counts: { entries: 4, provisional: 0, cited: 0, ownerAccepted: 4 },
      register: {
        factors: [
          {
            id: "roic",
            name: "Return on invested capital",
            group: "quality",
            direction: "higher",
            formula: "NOPAT_ttm / average(investedCapital)",
            parameters: { maxTaxRate: 0.35, defaultTaxRate: 0.21 },
            status: "owner_accepted",
            acceptedNote: "The register nets cash and averages invested capital.",
            citation: { quote: "ROIC = EBIT (1 – Tax Rate)/Total Capital" },
          },
          {
            id: "accruals",
            name: "Accruals",
            group: "quality",
            direction: "lower",
            formula: "(netIncome_ttm - operatingCashFlow_ttm) / avg(totalAssets)",
            parameters: {},
            status: "owner_accepted",
            acceptedNote: "No book in the knowledge base defines it.",
            citation: null,
          },
        ],
        composite: {
          status: "owner_accepted",
          groupWeights: { quality: 0.4, value: 0.3, trend: 0.3 },
          winsoriseStdDevs: 3,
          minSectorSize: 10,
          minFactorsPerGroupShare: 0.5,
          standardise: "zscore_within_sector",
          acceptedNote: "Within-sector z-scores and the group weights are an owner choice.",
          citation: { quote: "pull in all outliers in the Xn,k(t) to ±3 standard deviations about the mean." },
        },
        screen: {
          status: "owner_accepted",
          shortlistSize: 60,
          hardFilters: [{ id: "debtCeiling", field: "netDebtToEbitda", op: "<=", value: 4 }],
          acceptedNote: "Owner choice. No book prescribes these thresholds.",
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
    expect(screen.getAllByText("owner_accepted").length).toBeGreaterThan(0);
    expect(screen.getByText("Owner accepted").closest(".admin-kpi")).toHaveTextContent("4");
    expect(screen.getByText(/Winsorise at ±3 standard deviations/)).toBeInTheDocument();
    expect(screen.getByText("No book in the knowledge base defines it.")).toBeInTheDocument();
    expect(screen.getByText("The register nets cash and averages invested capital.")).toBeInTheDocument();
    expect(screen.getByText("ROIC = EBIT (1 – Tax Rate)/Total Capital")).toBeInTheDocument();
    expect(screen.getByText("Within-sector z-scores and the group weights are an owner choice.")).toBeInTheDocument();
    expect(screen.getByText(/pull in all outliers/)).toBeInTheDocument();
    expect(screen.getByText("Owner choice. No book prescribes these thresholds.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Return on invested capital" }));
    expect(document.querySelector(".admin-expand.is-open")).toHaveTextContent("maxTaxRate 0.35");
    expect(document.querySelector(".admin-expand.is-open")).toHaveTextContent("higher");
    expect(document.querySelector(".admin-expand.is-open")).toHaveTextContent("The register nets cash and averages invested capital.");
    expect(screen.getByText(/quality 0.4/)).toBeInTheDocument();
    expect(screen.getByText("netDebtToEbitda <= 4")).toBeInTheDocument();
  });
});
