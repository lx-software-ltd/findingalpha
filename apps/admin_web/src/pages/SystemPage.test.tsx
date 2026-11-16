import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SystemPage } from "./SystemPage";

const fetchJson = vi.fn();

vi.mock("../lib/apiAdminClient", () => ({
  adminFetchJson: (...args: unknown[]) => fetchJson(...args),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SystemPage />
    </QueryClientProvider>,
  );
}

describe("SystemPage", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
      this.open = false;
    };
    fetchJson.mockReset();
    fetchJson.mockImplementation((path: string, init?: { method?: string }) => {
      if (path === "/system/status") {
        return Promise.resolve({
          switches: [],
          brokerMode: "paper",
          jobs: [
            {
              job: "ingest_daily",
              schedule: "0 6",
              manualRun: true,
              progress: { status: "running", cursor: 9, total: 131 },
              lastRun: { status: "partial", startedAt: "2026-01-01T00:00:00.000Z", durationMs: 1, message: "9 of 131, continues on the next tick" },
            },
          ],
        });
      }
      if (String(path).startsWith("/jobs/runs")) return Promise.resolve({ runs: [] });
      if (path === "/api-keys") return Promise.resolve({ keys: [], writesEnabled: false });
      if (path === "/universe/latest") {
        return Promise.resolve({
          asOf: "2024-06-03",
          members: 4,
          counts: { marketCap: 4 },
          coverage: { flows: { revenue: 0.5 }, stocks: {} },
          lastPriceDate: "2024-06-03",
          backfill: { prices: { cursor: 2, total: 8 }, fundamentals: null },
        });
      }
      if (init?.method === "POST") return Promise.resolve({ accepted: true });
      return Promise.resolve({});
    });
  });

  it("shows the universe and confirms a run", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findAllByText("partial · 9 of 131")).toHaveLength(2);
    expect(await screen.findByText(/Universe 2024-06-03, 4 names/)).toBeTruthy();
    expect(screen.getByText(/2 of 8/)).toBeTruthy();
    expect(screen.getByText("revenue")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Run now" }));
    expect(screen.getByText("Run ingest_daily now?")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Accepted ingest_daily.");
    expect(fetchJson).toHaveBeenCalledWith("/jobs/ingest_daily/run", { method: "POST" });
  });

  it("renders before a universe exists", async () => {
    fetchJson.mockImplementation((path: string) => {
      if (path === "/system/status") return Promise.resolve({ switches: [], brokerMode: "paper", jobs: [] });
      if (String(path).startsWith("/jobs/runs")) return Promise.resolve({ runs: [] });
      if (path === "/api-keys") return Promise.resolve({ keys: [], writesEnabled: false });
      if (path === "/universe/latest") return Promise.resolve({ asOf: null, members: 0, counts: {} });
      return Promise.resolve({});
    });
    renderPage();
    expect(await screen.findByText(/Universe —, 0 names/)).toBeTruthy();
    expect(screen.getByText(/Price backfill —/)).toBeTruthy();
  });
});
