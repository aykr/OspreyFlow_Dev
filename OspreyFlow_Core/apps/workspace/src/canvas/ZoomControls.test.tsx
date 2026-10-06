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
});
