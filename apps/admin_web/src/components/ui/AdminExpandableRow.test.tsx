import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AdminExpandableRow, AdminExpandButton } from "./AdminExpandableRow";

describe("AdminExpandableRow", () => {
  it("shows the editor only while the row is open", () => {
    const { rerender } = render(
      <table>
        <AdminExpandableRow colSpan={1} expanded={false} onToggle={() => undefined} editor={<p>Editor</p>}>
          <td><AdminExpandButton>Alpha</AdminExpandButton></td>
        </AdminExpandableRow>
      </table>,
    );
    expect(screen.queryByText("Editor")).toBeNull();
    expect(screen.getByRole("button", { name: "Alpha" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("row", { name: "Alpha" })).not.toHaveAttribute("tabindex");
    rerender(
      <table>
        <AdminExpandableRow colSpan={1} expanded onToggle={() => undefined} editor={<p>Editor</p>}>
          <td><AdminExpandButton>Alpha</AdminExpandButton></td>
        </AdminExpandableRow>
      </table>,
    );
    expect(screen.getByText("Editor").closest(".admin-expand")).toHaveClass("is-open");
    expect(screen.getByRole("button", { name: "Alpha" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("row", { name: "Alpha" })).toHaveClass("admin-row-framed");
  });

  it("does not toggle when the editor is clicked", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(
      <table>
        <AdminExpandableRow colSpan={1} expanded onToggle={onToggle} editor={<button type="button">Inside</button>}>
          <td><AdminExpandButton>Alpha</AdminExpandButton></td>
        </AdminExpandableRow>
      </table>,
    );
    await user.click(screen.getByRole("button", { name: "Inside" }));
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("toggles from the button and ignores a selection inside the row", () => {
    const onToggle = vi.fn();
    render(
      <table>
        <AdminExpandableRow colSpan={1} expanded={false} onToggle={onToggle} editor={<p>Editor</p>}>
          <td><AdminExpandButton>Alpha</AdminExpandButton></td>
        </AdminExpandableRow>
      </table>,
    );
    const row = screen.getByRole("row", { name: "Alpha" });
    fireEvent.keyDown(row, { key: "Enter" });
    expect(onToggle).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Alpha" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    const label = screen.getByRole("button", { name: "Alpha" });
    vi.spyOn(window, "getSelection").mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      anchorNode: label.firstChild,
      toString: () => "Alpha",
    } as Selection);
    fireEvent.click(row);
    expect(onToggle).toHaveBeenCalledTimes(1);
    vi.restoreAllMocks();
  });

  it("still toggles when text is selected outside the row", () => {
    const onToggle = vi.fn();
    render(
      <table>
        <AdminExpandableRow colSpan={1} expanded={false} onToggle={onToggle} editor={<p>Editor</p>}>
          <td>Alpha</td>
        </AdminExpandableRow>
      </table>,
    );
    vi.spyOn(window, "getSelection").mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      anchorNode: document.body,
      toString: () => "elsewhere",
    } as Selection);
    fireEvent.click(screen.getByRole("row", { name: "Alpha" }));
    expect(onToggle).toHaveBeenCalledTimes(1);
    vi.restoreAllMocks();
  });
});
