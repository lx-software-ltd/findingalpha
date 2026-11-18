import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { KnowledgeBasePage } from "./KnowledgeBasePage";

const fetchJson = vi.fn();

vi.mock("../lib/apiAdminClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/apiAdminClient")>("../lib/apiAdminClient");
  return { ...actual, adminFetchJson: (...args: unknown[]) => fetchJson(...args) };
});

const status = {
  documents: 131,
  bytes: 500_000_000,
  capBytes: 2_000_000_000,
  retrievals: 2500,
  retrievalCap: 5000,
  syncedAt: "2026-11-18T01:00:00.000Z",
  status: "blocked_deletion",
  running: false,
  stopping: false,
  progress: null,
  evaluation: { ranAt: "2026-11-18T02:00:00.000Z", questions: 20, hitAt8: 16, hitAt3: 12 },
  problems: [{ key: "theory/scan.pdf", problem: "too_large" }],
  failedDocuments: ["theory/broken.pdf"],
  blocked: { status: "blocked_deletion" },
  blockedReason: "More than 15% of a folder is gone: theory/ lost 20 of 100.",
  cost: { storageUsd: 2.5, retrievalUsd: 2.5 },
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <KnowledgeBasePage />
    </QueryClientProvider>,
  );
}

describe("KnowledgeBasePage", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
      this.open = true;
    };
    HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
      this.open = false;
    };
    fetchJson.mockReset();
    fetchJson.mockImplementation((path: string, init?: { method?: string }) => {
      if (path === "/kb/status") return Promise.resolve(status);
      if (path === "/kb/eval/latest") {
        return Promise.resolve({
          ranAt: "2026-11-18T02:00:00.000Z",
          questions: 20,
          hitAt8: 16,
          hitAt3: 12,
          results: [{ id: "q01", rank: 2 }, { id: "q02", rank: null }],
        });
      }
      if (init?.method === "POST") return Promise.resolve({ accepted: true });
      return Promise.resolve({});
    });
  });

  it("shows the caps, the problems, and the question ranks", async () => {
    renderPage();
    expect(await screen.findByText("131")).toBeTruthy();
    expect(screen.getByText("0.50 GB")).toBeTruthy();
    expect(screen.getByText("2,500")).toBeTruthy();
    expect(screen.getByText("16 of 20 in the top 8")).toBeTruthy();
    expect(screen.getAllByText("$2.50")).toHaveLength(2);
    expect(screen.getByText("Storage for a month")).toBeTruthy();
    expect(screen.getByText("Retrievals so far")).toBeTruthy();
    expect(screen.getByText("waiting for confirmation")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Sync now" })).toBeNull();
    expect(screen.getByText("theory/scan.pdf: larger than 50 MB")).toBeTruthy();
    expect(screen.getByText("theory/broken.pdf: failed during sync")).toBeTruthy();
    expect(screen.getByText("q01")).toBeTruthy();
    expect(screen.getByText("miss")).toBeTruthy();
    expect(screen.getByText(/theory\/ lost 20 of 100/)).toBeTruthy();
  });

  it("confirms a deletion and can stop a running sync", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Confirm deletion" }));
    expect(screen.getByText("More than 15% of a folder is gone. Sync anyway?")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Sync" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Deletion confirmed");
    expect(fetchJson).toHaveBeenCalledWith("/kb/sync", {
      method: "POST",
      body: JSON.stringify({ confirmDeletion: true }),
    });
    fetchJson.mockImplementation((path: string, init?: { method?: string }) => {
      if (path === "/kb/status") {
        return Promise.resolve({
          ...status,
          running: true,
          status: "running",
          blocked: null,
          blockedReason: null,
          progress: { scanned: 12, indexed: 4, failed: 1 },
        });
      }
      if (path === "/kb/eval/latest") return Promise.resolve({ results: [] });
      if (init?.method === "POST") return Promise.resolve({ accepted: true });
      return Promise.resolve({});
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Stop" }));
    await user.click(screen.getByRole("button", { name: "Stop sync" }));
    expect(fetchJson).toHaveBeenCalledWith("/kb/sync", {
      method: "POST",
      body: JSON.stringify({ stop: true }),
    });
    expect(screen.getByText("Scanned 12, indexed 4, 1 failed.")).toBeTruthy();
  });

  it("starts a sync and an evaluation", async () => {
    const user = userEvent.setup();
    fetchJson.mockImplementation((path: string, init?: { method?: string }) => {
      if (path === "/kb/status") {
        return Promise.resolve({ ...status, status: "done", blocked: null, blockedReason: null, syncedAt: status.syncedAt });
      }
      if (path === "/kb/eval/latest") return Promise.resolve({ results: [{ id: "q01", rank: 2 }] });
      if (init?.method === "POST") return Promise.resolve({ accepted: true });
      return Promise.resolve({});
    });
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Sync now" }));
    await user.click(screen.getByRole("button", { name: "Sync" }));
    expect(fetchJson).toHaveBeenCalledWith("/kb/sync", { method: "POST" });
    await user.click(screen.getByRole("button", { name: "Run evaluation" }));
    await user.click(screen.getByRole("button", { name: "Start evaluation" }));
    expect(fetchJson).toHaveBeenCalledWith("/jobs/kb_eval/run", { method: "POST" });
  });
});
