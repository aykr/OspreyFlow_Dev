// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(cleanup);

import { ZoomControls } from "./ZoomControls";

// ADR-097 step 2, design review item 10: a zoom cluster on the canvas, with Fit (F).
describe("ZoomControls", () => {
  it("is one group, Zoom, of Zoom in, Zoom out and Fit to view, each doing its own thing", () => {
    const onZoomIn = vi.fn();
    const onZoomOut = vi.fn();
    const onFit = vi.fn();
    const { getByRole } = render(<ZoomControls onZoomIn={onZoomIn} onZoomOut={onZoomOut} onFit={onFit} />);
    expect(getByRole("group", { name: "Zoom" })).toBeTruthy();
    fireEvent.click(getByRole("button", { name: "Zoom in" }));
    fireEvent.click(getByRole("button", { name: "Zoom out" }));
    fireEvent.click(getByRole("button", { name: "Fit to view" }));
    expect([onZoomIn.mock.calls.length, onZoomOut.mock.calls.length, onFit.mock.calls.length]).toEqual([1, 1, 1]);
  });

  it("names F as Fit's shortcut", () => {
    const { getByRole } = render(<ZoomControls onZoomIn={() => {}} onZoomOut={() => {}} onFit={() => {}} />);
    expect(getByRole("button", { name: "Fit to view" }).getAttribute("aria-keyshortcuts")).toBe("F");
  });

  // ADR-115 E4 (review item 10; the reference's zoom group): out, the zoom as a percentage in mono,
  // in, then Fit — top to bottom.
  it("reads out the zoom between Zoom out and Zoom in, in mono", () => {
    const { getByRole, getByText } = render(<ZoomControls onZoomIn={() => {}} onZoomOut={() => {}} onFit={() => {}} percent={125} />);
    const group = getByRole("group", { name: "Zoom" });
    const order = Array.from(group.children).map((c) => c.getAttribute("aria-label") ?? c.textContent);
    expect(order).toEqual(["Zoom out", "Zoom 125%", "Zoom in", "Fit to view"]);
    expect(getByText("125%").className).toContain("value");
    expect((getByText("125%").closest(".canvas-zoom__readout") as HTMLElement).hidden).toBe(false);
  });
});
