import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AdminFilterBar, AdminFilterField, AdminRecordTable } from "./AdminRecordTable";

describe("AdminRecordTable", () => {
  it("wraps the table in a labelled card and shows the filter", () => {
    render(
      <AdminRecordTable
        label="Shortlist"
        filters={
          <AdminFilterBar>
            <AdminFilterField label="Date" htmlFor="screen-date">
              <input id="screen-date" type="date" />
            </AdminFilterField>
          </AdminFilterBar>
        }
      >
        <p>Rows</p>
      </AdminRecordTable>,
    );
    expect(screen.getByRole("region", { name: "Shortlist" })).toHaveClass("admin-record-table");
    expect(screen.getByLabelText("Date")).toBeInTheDocument();
    expect(screen.getByText("Rows")).toBeInTheDocument();
  });
});
