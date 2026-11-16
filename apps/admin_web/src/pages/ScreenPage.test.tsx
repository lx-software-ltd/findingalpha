import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
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
    expect(await screen.findByRole("button", { name: "AAA" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "AAA" }));
    expect(screen.getByText(/roic: 0.20/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Backtest" }));
    expect(await screen.findByRole("img", { name: "Backtest equity curves" })).toBeInTheDocument();
    expect(screen.getByText(/Known biases/)).toBeInTheDocument();
  });
});
