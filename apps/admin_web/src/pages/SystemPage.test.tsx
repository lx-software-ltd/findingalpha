import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AdminApiError } from "../lib/apiAdminClient";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SystemPage } from "./SystemPage";

const fetchJson = vi.fn();

vi.mock("../lib/apiAdminClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/apiAdminClient")>("../lib/apiAdminClient");
  return { ...actual, adminFetchJson: (...args: unknown[]) => fetchJson(...args) };
});

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
    expect(await screen.findAllByRole("cell", { name: /partial · 9 of 131/ })).toHaveLength(2);
    expect(screen.getByText(/0 6 · partial · 9 of 131/)).toBeInTheDocument();
    expect(await screen.findByText("4 names")).toBeTruthy();
    expect(screen.getAllByText("2024-06-03").length).toBeGreaterThan(0);
    expect(screen.getByText("paper")).toBeTruthy();
    expect(screen.getByText("Price backfill").parentElement).toHaveTextContent("2 of 8");
    expect(screen.getByText("revenue")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Run now" }));
    expect(screen.getByText("Run ingest_daily now?")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Accepted ingest_daily.");
    expect(fetchJson).toHaveBeenCalledWith("/jobs/ingest_daily/run", { method: "POST" });
  });

  it("asks for a backtest size and sends an integer", async () => {
    fetchJson.mockImplementation((path: string, init?: { method?: string; body?: string }) => {
      if (path === "/system/status") {
        return Promise.resolve({
          switches: [],
          brokerMode: "paper",
          jobs: [
            { job: "ingest_daily", schedule: "0 6", manualRun: true, lastRun: null },
            { job: "backtest", schedule: "", manualRun: true, lastRun: null },
          ],
        });
      }
      if (String(path).startsWith("/jobs/runs")) return Promise.resolve({ runs: [] });
      if (path === "/api-keys") return Promise.resolve({ keys: [], writesEnabled: false });
      if (path === "/universe/latest") {
        return Promise.resolve({ asOf: null, members: 0, counts: {} });
      }
      if (init?.method === "POST") {
        const sent = typeof init?.body === "string" ? JSON.parse(init.body) : {};
        return Promise.resolve({ accepted: true, ...(sent.portfolioSize ? { portfolioSize: sent.portfolioSize } : {}) });
      }
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderPage();
    const row = await screen.findByRole("row", { name: /backtest/ });
    await user.click(within(row).getByRole("button", { name: "Run now" }));
    const names = screen.getByRole("spinbutton", { name: "Names" });
    expect(names).toHaveValue(20);
    expect(screen.getByText(/10 to 40/)).toBeTruthy();
    expect(screen.getByText(/Leave 20/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Accepted backtest.");
    expect(fetchJson).toHaveBeenCalledWith("/jobs/backtest/run", { method: "POST" });
    await user.click(within(row).getByRole("button", { name: "Run now" }));
    const again = screen.getByRole("spinbutton", { name: "Names" });
    await user.clear(again);
    await user.type(again, "9");
    expect(screen.getByRole("button", { name: "Run" })).toBeDisabled();
    await user.clear(again);
    await user.type(again, "15");
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Accepted backtest, 15 names.");
    expect(fetchJson).toHaveBeenCalledWith("/jobs/backtest/run", {
      method: "POST",
      body: JSON.stringify({ portfolioSize: 15 }),
    });
  });

  it("shows a refusal and an unconfirmed size", async () => {
    fetchJson.mockImplementation((path: string, init?: { method?: string }) => {
      if (path === "/system/status") {
        return Promise.resolve({
          switches: [],
          brokerMode: "paper",
          jobs: [{ job: "backtest", schedule: "", manualRun: true, lastRun: null }],
        });
      }
      if (String(path).startsWith("/jobs/runs")) return Promise.resolve({ runs: [] });
      if (path === "/api-keys") return Promise.resolve({ keys: [], writesEnabled: false });
      if (path === "/universe/latest") return Promise.resolve({ asOf: null, members: 0, counts: {} });
      if (init?.method === "POST") return Promise.resolve({ accepted: true });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Run now" }));
    await user.clear(screen.getByRole("spinbutton", { name: "Names" }));
    await user.type(screen.getByRole("spinbutton", { name: "Names" }), "15");
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("did not confirm 15 names");
    fetchJson.mockImplementation((path: string, init?: { method?: string }) => {
      if (init?.method === "POST") {
        return Promise.reject(new AdminApiError(409, JSON.stringify({ message: "unfinished backtest is 15 names" })));
      }
      return Promise.resolve({});
    });
    await user.click(screen.getByRole("button", { name: "Run now" }));
    await user.clear(screen.getByRole("spinbutton", { name: "Names" }));
    await user.type(screen.getByRole("spinbutton", { name: "Names" }), "30");
    await user.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("unfinished backtest is 15 names");
  });

  it("confirms a deletion and stops a running sync", async () => {
    fetchJson.mockImplementation((path: string, init?: { method?: string; body?: string }) => {
      if (path === "/system/status") {
        return Promise.resolve({
          switches: [],
          brokerMode: "paper",
          jobs: [
            {
              job: "kb_sync_check",
              schedule: "30 5",
              manualRun: true,
              lastRun: {
                status: "failed",
                startedAt: "2026-01-01T00:00:00.000Z",
                durationMs: 1,
                message: "blocked_deletion: theory/ 50 of 100",
              },
            },
          ],
        });
      }
      if (String(path).startsWith("/jobs/runs")) return Promise.resolve({ runs: [] });
      if (path === "/api-keys") return Promise.resolve({ keys: [], writesEnabled: false });
      if (path === "/universe/latest") return Promise.resolve({ asOf: null, members: 0, counts: {} });
      if (init?.method === "POST") return Promise.resolve({ accepted: true });
      return Promise.resolve({});
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Confirm deletion" }));
    expect(screen.getByText("More than 15% of a folder is gone. Sync anyway?")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Sync" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Accepted kb_sync_check, deletion confirmed.");
    expect(fetchJson).toHaveBeenCalledWith("/jobs/kb_sync_check/run", {
      method: "POST",
      body: JSON.stringify({ confirmDeletion: true }),
    });
    fetchJson.mockImplementation((path: string, init?: { method?: string }) => {
      if (path === "/system/status") {
        return Promise.resolve({
          switches: [],
          brokerMode: "paper",
          jobs: [
            {
              job: "kb_sync_check",
              schedule: "30 5",
              manualRun: true,
              lastRun: {
                status: "partial",
                startedAt: "2026-01-01T00:00:00.000Z",
                durationMs: 1,
                message: "continues on the next tick",
              },
            },
          ],
        });
      }
      if (init?.method === "POST") return Promise.resolve({ accepted: true });
      return Promise.resolve({});
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    expect(screen.getByText("Stop the knowledge base sync that is running?")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Stop sync" }));
    expect(fetchJson).toHaveBeenCalledWith("/jobs/kb_sync_check/run", {
      method: "POST",
      body: JSON.stringify({ stop: true }),
    });
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
    expect(await screen.findByText("0 names")).toBeTruthy();
    expect(screen.getByText("Universe").parentElement).toHaveTextContent("No as-of date");
    expect(screen.getByText("Price backfill").parentElement).toHaveTextContent("—");
  });
});
