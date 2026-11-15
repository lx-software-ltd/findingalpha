import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RoadmapPage } from "./RoadmapPage";

const fetchJson = vi.fn();

vi.mock("../lib/apiAdminClient", () => ({
  adminFetchJson: (...args: unknown[]) => fetchJson(...args),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RoadmapPage />
    </QueryClientProvider>,
  );
}

describe("RoadmapPage", () => {
  beforeEach(() => {
    fetchJson.mockReset();
    fetchJson.mockResolvedValue({ done: {} });
  });

  it("renders the step counts", async () => {
    renderPage();
    expect(await screen.findByText("0 / 118")).toBeTruthy();
    expect(screen.getByText("Blocked by O02, O03")).toBeTruthy();
  });

  it("reverts a tick when the API fails", async () => {
    const user = userEvent.setup();
    renderPage();
    const box = await screen.findByRole("checkbox", { name: "O02" });
    fetchJson.mockRejectedValueOnce(new Error("500"));
    await user.click(box);
    expect(fetchJson).toHaveBeenCalledWith("/owner-tasks/O02", expect.objectContaining({ method: "PUT" }));
    expect(box).not.toBeChecked();
  });
});
