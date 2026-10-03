// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LayoutMenu } from "./LayoutMenu";

afterEach(cleanup);

function setup(mode: Parameters<typeof LayoutMenu>[0]["mode"] = "organic") {
  const handlers = { onChange: vi.fn(), onArrange: vi.fn() };
  render(<LayoutMenu mode={mode} {...handlers} />);
  return handlers;
}

describe("LayoutMenu", () => {
  it("offers all seven layouts", () => {
    setup();
    const names = screen.getAllByRole("option").map((o) => o.textContent);
    expect(names).toEqual([
      "Organic",
      "Radial around selected node",
      "Hierarchical",
      "Circular",
      "Group by type",
      "Force-directed tree",
      "Clustered bubbles",
    ]);
  });

  it("shows the layout in use", () => {
    setup("hierarchical");
    expect((screen.getByRole("combobox", { name: "Layout" }) as HTMLSelectElement).value).toBe("hierarchical");
  });

  it("reports the layout chosen", () => {
    const h = setup();
    fireEvent.change(screen.getByRole("combobox", { name: "Layout" }), { target: { value: "circular" } });
    expect(h.onChange).toHaveBeenCalledWith("circular");
  });

  it("offers what the bubbles hold only while Clustered bubbles is the layout", () => {
    const { rerender } = render(<LayoutMenu mode="organic" onChange={vi.fn()} onArrange={vi.fn()} onBubbleKeyChange={vi.fn()} />);
    expect(screen.queryByRole("combobox", { name: "Bubbles by" })).toBeNull();
    const change = vi.fn();
    rerender(<LayoutMenu mode="bubbles" onChange={vi.fn()} onArrange={vi.fn()} onBubbleKeyChange={change} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Bubbles by" }), { target: { value: "community" } });
    expect(change).toHaveBeenCalledWith("community");
  });

  it("can arrange again with the layout in use, without changing it", () => {
    const h = setup("radial");
    fireEvent.click(screen.getByRole("button", { name: "Arrange again" }));
    expect(h.onArrange).toHaveBeenCalledOnce();
    expect(h.onChange).not.toHaveBeenCalled();
  });
});
