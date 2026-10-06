// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(cleanup);

import { CanvasLegend } from "./CanvasLegend";

// ADR-097 step 2, design review item 10: a legend of the types present, as the canvas draws them.
describe("CanvasLegend", () => {
  const types = [
    { type: "Person", count: 12, visual: { channel: "indigo", shape: "circle", icon: null } as const },
    { type: "Phone", count: 3, visual: { channel: "cyan", shape: "hexagon", icon: null } as const },
  ];

  it("lists each type in view with its count, most first", () => {
    const { getByRole } = render(<CanvasLegend types={types} />);
    const list = getByRole("list", { name: "Types in view" });
    const rows = Array.from(list.querySelectorAll("li")).map((li) => li.textContent);
    expect(rows).toEqual(["Person12", "Phone3"]);
    expect(list.querySelectorAll("img")).toHaveLength(2);
  });

  it("folds and opens from its own button, keeping the list in the page", () => {
    const { container, getByRole } = render(<CanvasLegend types={types} />);
    const toggle = getByRole("button", { name: "Legend" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    const list = container.querySelector<HTMLUListElement>('ul[aria-label="Types in view"]');
    expect(list?.hidden).toBe(true);
  });

  it("is not drawn for an empty view", () => {
    const { container } = render(<CanvasLegend types={[]} />);
    expect(container.textContent).toBe("");
  });
});
