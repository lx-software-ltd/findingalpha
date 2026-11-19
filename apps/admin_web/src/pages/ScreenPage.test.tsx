import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { backtestFixture, backtestListFixture, screenFixture } from "../lib/mock/fixtures";
import { ScreenPage } from "./ScreenPage";

const fetchJson = vi.fn();

vi.mock("../lib/apiAdminClient", () => ({
  adminFetchJson: (...args: unknown[]) => fetchJson(...args),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ScreenPage />
    </QueryClientProvider>,
  );
}

function rowPrecedes(first: string, second: string): boolean {
  const earlier = screen.getByRole("row", { name: new RegExp(first) });
  const later = screen.getByRole("row", { name: new RegExp(second) });
  return Boolean(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING);
}

describe("ScreenPage", () => {
  beforeEach(() => {
    fetchJson.mockReset();
    fetchJson.mockImplementation((path: string) => {
      if (path === "/screens/latest") return Promise.resolve(screenFixture);
      if (path === "/backtests") return Promise.resolve({ runs: backtestListFixture });
      if (path === "/backtests/run-example") return Promise.resolve(backtestFixture);
      return Promise.reject(new Error("missing"));
    });
  });

  it("lists the shortlist and opens the equity curves", async () => {
    renderPage();
    const aaa = await screen.findByRole("row", { name: /AAA/ });
    const openAaa = within(aaa).getByRole("button", { name: "AAA" });
    expect(openAaa).toHaveAttribute("aria-expanded", "false");
    expect(aaa).not.toHaveAttribute("tabindex");
    expect(within(aaa).getByText(/Rank 1/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Screen" })).toHaveClass("admin-page-title");
    expect(screen.getByRole("columnheader", { name: /Rank/ })).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getByRole("columnheader", { name: "roic" })).toBeInTheDocument();
    expect(screen.getByLabelText("Sort")).toHaveClass("form-select");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Symbol" }));
    expect(screen.getByRole("columnheader", { name: /Symbol/ })).toHaveAttribute("aria-sort", "ascending");
    fireEvent.click(screen.getByRole("button", { name: /Sorted by Symbol, ascending/ }));
    expect(screen.getByRole("columnheader", { name: /Symbol/ })).toHaveAttribute("aria-sort", "descending");
    expect(rowPrecedes("BBB", "AAA")).toBe(true);
    fireEvent.change(screen.getByLabelText("Sort"), { target: { value: "composite:asc" } });
    expect(screen.getByRole("columnheader", { name: /Composite/ })).toHaveAttribute("aria-sort", "ascending");
    expect(rowPrecedes("BBB", "AAA")).toBe(true);
    fireEvent.click(openAaa);
    const open = document.querySelector(".admin-expand.is-open");
    expect(openAaa).toHaveAttribute("aria-expanded", "true");
    expect(open).toHaveTextContent(/roic: 0.20/);
    expect(open).toHaveTextContent("Sector: tech");
    expect(open).toHaveTextContent("Quality: 0.40");
    expect(document.querySelector(".admin-expand:not(.is-open)")).toBeNull();
    expect(screen.getByLabelText("Date").closest(".admin-filter-field")).toHaveClass("admin-filter-field-compact");
    expect(screen.queryByRole("alert")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Backtest" }));
    expect(await screen.findByRole("img", { name: "Backtest equity curves" })).toBeInTheDocument();
    expect(screen.getAllByText("2017-02").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SPY net").length).toBeGreaterThan(0);
    expect(screen.getByText(/Worst 12 months/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: /Full · Strategy · CAGR 8.0%/ })).toHaveTextContent("CAGR 8.0%");
    expect(screen.getByRole("cell", { name: /Full · SPY net · CAGR 4.0%/ })).toBeInTheDocument();
    expect(screen.getByText(/Known biases/)).toBeInTheDocument();
    expect(screen.getByText(/a missing SIC excludes it/)).toBeInTheDocument();
  });

  it("says a screen is missing only when the response is not found", async () => {
    fetchJson.mockImplementation((path: string) => {
      if (path === "/screens/latest") return Promise.reject({ status: 500 });
      if (path === "/screens/2017-01-01") return Promise.reject({ status: 404 });
      return Promise.resolve({ runs: [] });
    });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("The screen could not be loaded.");
    expect(screen.getByRole("alert")).toHaveClass("alert");
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "2017-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Load date" }));
    expect(await screen.findByText("That screen is not stored.")).toBeInTheDocument();
  });

  it("sorts missing composites last and breaks rank ties by symbol", async () => {
    fetchJson.mockImplementation((path: string) => {
      if (path === "/screens/latest") {
        const [first, second] = screenFixture.rows;
        return Promise.resolve({
          ...screenFixture,
          rows: [
            { ...second, symbol: "BBB", rank: 1, composite: -0.2 },
            { ...first, symbol: "AAA", rank: 1, composite: -0.2 },
            { ...first, symbol: "CCC", rank: 3, composite: null },
          ],
        });
      }
      return Promise.resolve({ runs: [] });
    });
    renderPage();
    await screen.findByRole("button", { name: "AAA" });
    expect(rowPrecedes("AAA", "BBB")).toBe(true);
    expect(rowPrecedes("BBB", "CCC")).toBe(true);
    fireEvent.change(screen.getByLabelText("Sort"), { target: { value: "composite:desc" } });
    expect(rowPrecedes("BBB", "CCC")).toBe(true);
    expect(rowPrecedes("AAA", "CCC")).toBe(true);
  });

  it("keeps one run select and reports a failed backtest", async () => {
    let resolveDetail: (value: unknown) => void = () => undefined;
    let rejectOther: (error: unknown) => void = () => undefined;
    const detailPromise = new Promise((resolve) => {
      resolveDetail = resolve;
    });
    const otherPromise = new Promise((_resolve, reject) => {
      rejectOther = reject;
    });
    fetchJson.mockImplementation((path: string) => {
      if (path === "/screens/latest") return Promise.resolve(screenFixture);
      if (path === "/backtests") return Promise.resolve({ runs: backtestListFixture });
      if (path === "/backtests/run-example") return detailPromise;
      if (path === "/backtests/run-other") return otherPromise;
      return Promise.reject(new Error("missing"));
    });
    renderPage();
    fireEvent.click(await screen.findByRole("tab", { name: "Backtest" }));
    const select = await screen.findByLabelText("Run");
    expect(screen.getAllByLabelText("Run")).toHaveLength(1);
    resolveDetail(backtestFixture);
    expect(await screen.findByRole("img", { name: "Backtest equity curves" })).toBeInTheDocument();
    expect(screen.getByLabelText("Run")).toBe(select);
    select.focus();
    fireEvent.change(select, { target: { value: "run-other" } });
    await waitFor(() => expect(fetchJson).toHaveBeenCalledWith("/backtests/run-other"));
    expect(screen.getByLabelText("Run")).toBe(select);
    expect(document.activeElement).toBe(select);
    expect(screen.getByRole("img", { name: "Backtest equity curves" })).toBeInTheDocument();
    rejectOther(new Error("no"));
    expect(await screen.findByRole("alert")).toHaveTextContent("The backtest could not be loaded.");
    expect(screen.getByLabelText("Run")).toBe(select);
  });
});
