import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LineChart } from "./LineChart";

describe("LineChart", () => {
  it("draws one path per series and a message when there is nothing to plot", () => {
    const { container, rerender } = render(
      <LineChart
        title="Equity"
        series={[
          { name: "Strategy", colour: "#0d6efd", points: [{ x: "a", y: 1 }, { x: "b", y: 2 }] },
          { name: "SPY", colour: "#6c757d", points: [{ x: "a", y: 1 }, { x: "b", y: 1.5 }] },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "Equity" })).toBeInTheDocument();
    expect(container.querySelectorAll("path")).toHaveLength(2);
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("b")).toBeInTheDocument();
    rerender(<LineChart title="Equity" series={[{ name: "Empty", colour: "#000", points: [] }]} />);
    expect(screen.getByText("No series to plot.")).toBeInTheDocument();
  });
});
