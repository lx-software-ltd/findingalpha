import { memo } from "react";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AdminDataTable } from "./AdminDataTable";
import { AdminExpandableRow } from "./AdminExpandableRow";

const MemoRow = memo(AdminExpandableRow);

describe("AdminDataTable record groups", () => {
  it("does not nest a tbody when the row is wrapped in memo", () => {
    const { container } = render(
      <AdminDataTable bare columns={[{ key: "name", header: "Name" }]}>
        <MemoRow colSpan={1} expanded={false} onToggle={() => undefined} editor={<p>Editor</p>}>
          <td>Alpha</td>
        </MemoRow>
      </AdminDataTable>,
    );
    expect(container.querySelector("tbody tbody")).toBeNull();
    expect(container.querySelectorAll("tbody")).toHaveLength(1);
  });

  it("warns when a tbody is nested", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    function Plain() {
      return (
        <tbody>
          <tr>
            <td>Alpha</td>
          </tr>
        </tbody>
      );
    }
    render(
      <AdminDataTable bare columns={[{ key: "name", header: "Name" }]}>
        <Plain />
      </AdminDataTable>,
    );
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("tbody inside a tbody"));
    warn.mockRestore();
  });
});
