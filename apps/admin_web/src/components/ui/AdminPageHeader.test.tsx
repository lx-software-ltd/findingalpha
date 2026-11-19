import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AdminPageHeader } from "./AdminPageHeader";

describe("AdminPageHeader", () => {
  it("shows the eyebrow, the title, and the actions", () => {
    render(
      <AdminPageHeader eyebrow="Finding Alpha" title="Screen">
        <button type="button">Load date</button>
      </AdminPageHeader>,
    );
    expect(screen.getByText("Finding Alpha")).toHaveClass("admin-eyebrow");
    expect(screen.getByRole("heading", { name: "Screen" })).toHaveClass("admin-page-title");
    expect(screen.getByRole("button", { name: "Load date" })).toBeInTheDocument();
  });
});
