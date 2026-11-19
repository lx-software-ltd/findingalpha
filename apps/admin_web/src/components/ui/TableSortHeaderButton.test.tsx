import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TableSortHeaderButton } from "./TableSortHeaderButton";

describe("TableSortHeaderButton", () => {
  it("keeps the sort button for desktop and a static label for phones", () => {
    render(
      <TableSortHeaderButton
        label="Composite"
        isActive={false}
        direction={null}
        onClick={vi.fn()}
      />,
    );
    const button = screen.getByRole("button", { name: "Sort by Composite" });
    expect(button.className).toContain("d-none");
    expect(button.className).toContain("d-md-inline-block");
    expect(button.className).toContain("admin-sort-header");
    const phoneLabel = screen.getAllByText("Composite").find((el) => el.tagName === "SPAN");
    expect(phoneLabel?.className).toContain("d-md-none");
  });
});
