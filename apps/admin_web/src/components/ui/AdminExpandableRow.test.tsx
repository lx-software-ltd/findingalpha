import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AdminExpandableRow } from "./AdminExpandableRow";

describe("AdminExpandableRow", () => {
  it("shows the editor only while the row is open", () => {
    const { rerender } = render(
      <table>
        <AdminExpandableRow colSpan={1} expanded={false} onToggle={() => undefined} editor={<p>Editor</p>}>
          <td>Alpha</td>
        </AdminExpandableRow>
      </table>,
    );
    const closed = screen.getByText("Editor").closest(".admin-expand");
    expect(closed).not.toHaveClass("is-open");
    expect(closed?.closest("tr")).toHaveAttribute("aria-hidden", "true");
    rerender(
      <table>
        <AdminExpandableRow colSpan={1} expanded onToggle={() => undefined} editor={<p>Editor</p>}>
          <td>Alpha</td>
        </AdminExpandableRow>
      </table>,
    );
    const open = screen.getByText("Editor").closest(".admin-expand");
    expect(open).toHaveClass("is-open");
    expect(open?.closest("tr")).not.toHaveAttribute("aria-hidden");
    expect(screen.getByRole("row", { name: "Alpha" })).toHaveClass("admin-row-framed");
  });

  it("does not toggle when the editor is clicked", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <table>
        <AdminExpandableRow colSpan={1} expanded onToggle={onToggle} editor={<button type="button">Inside</button>}>
          <td>Alpha</td>
        </AdminExpandableRow>
      </table>,
    );
    await user.click(screen.getByRole("button", { name: "Inside" }));
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("toggles from the keyboard and ignores a text selection", () => {
    const onToggle = vi.fn();
    render(
      <table>
        <AdminExpandableRow colSpan={1} expanded={false} onToggle={onToggle} editor={<p>Editor</p>}>
          <td>Alpha</td>
        </AdminExpandableRow>
      </table>,
    );
    const row = screen.getByRole("row", { name: "Alpha" });
    fireEvent.keyDown(row, { key: "Enter" });
    expect(onToggle).toHaveBeenCalledTimes(1);
    vi.spyOn(window, "getSelection").mockReturnValue({
      isCollapsed: false,
      toString: () => "Alpha",
    } as Selection);
    fireEvent.click(row);
    expect(onToggle).toHaveBeenCalledTimes(1);
    vi.restoreAllMocks();
  });
});
