import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("renders only the centred Finding Alpha logo", () => {
    const { container } = render(<App />);
    const logo = screen.getByRole("img", { name: "Finding Alpha" });
    expect(logo).toHaveAttribute("src", "/logo.png");
    expect(container.querySelectorAll("img")).toHaveLength(1);
    expect(container.querySelectorAll("a, button, nav, form")).toHaveLength(0);
  });
});
