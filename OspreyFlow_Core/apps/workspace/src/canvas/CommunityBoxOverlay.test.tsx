// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommunityBoxOverlay } from "./CommunityBoxOverlay";

afterEach(cleanup);

/** A stand-in for Sigma: graph units are drawn at twice their size, shifted by (10, 20). */
function fakeSigma() {
  const listeners = new Set<() => void>();
  const sigma = {
    graphToViewport: ({ x, y }: { x: number; y: number }) => ({ x: x * 2 + 10, y: y * 2 + 20 }),
    on: (_: string, fn: () => void) => listeners.add(fn),
    removeListener: (_: string, fn: () => void) => listeners.delete(fn),
  };
  return { sigma, redraw: () => act(() => listeners.forEach((fn) => fn())), listeners };
}

const BOX = { id: "c:a", count: 4, x0: 0, y0: 0, x1: 50, y1: 30 };

describe("CommunityBoxOverlay", () => {
  it("draws one box per group at the viewport position of its corners", () => {
    const { sigma } = fakeSigma();
    render(<CommunityBoxOverlay sigmaRef={{ current: sigma as never }} getBoxes={() => [BOX]} onFold={() => undefined} />);
    const rect = document.querySelector("rect")!;
    expect(rect.getAttribute("x")).toBe("10");
    expect(rect.getAttribute("y")).toBe("20");
    expect(rect.getAttribute("width")).toBe("100");
    expect(rect.getAttribute("height")).toBe("60");
  });

  it("gives each box a button to fold that group, named by its size", () => {
    const { sigma } = fakeSigma();
    const onFold = vi.fn();
    render(<CommunityBoxOverlay sigmaRef={{ current: sigma as never }} getBoxes={() => [BOX]} onFold={onFold} />);
    fireEvent.click(screen.getByRole("button", { name: "Fold group of 4 nodes" }));
    expect(onFold).toHaveBeenCalledWith("c:a");
  });

  it("lets pointer events through the box itself, so the nodes under it stay clickable", () => {
    const { sigma } = fakeSigma();
    render(<CommunityBoxOverlay sigmaRef={{ current: sigma as never }} getBoxes={() => [BOX]} onFold={() => undefined} />);
    expect((document.querySelector("svg") as SVGElement).style.pointerEvents).toBe("none");
  });

  it("redraws when the canvas draws again (a camera move or the layout settling)", () => {
    const { sigma, redraw } = fakeSigma();
    let box = BOX;
    render(<CommunityBoxOverlay sigmaRef={{ current: sigma as never }} getBoxes={() => [box]} onFold={() => undefined} />);
    box = { ...BOX, x1: 100 };
    redraw();
    expect(document.querySelector("rect")!.getAttribute("width")).toBe("200");
  });

  it("stops listening when it is removed", () => {
    const { sigma, listeners } = fakeSigma();
    const { unmount } = render(<CommunityBoxOverlay sigmaRef={{ current: sigma as never }} getBoxes={() => [BOX]} onFold={() => undefined} />);
    expect(listeners.size).toBe(1);
    unmount();
    expect(listeners.size).toBe(0);
  });

  it("draws nothing when there are no groups", () => {
    const { sigma } = fakeSigma();
    render(<CommunityBoxOverlay sigmaRef={{ current: sigma as never }} getBoxes={() => []} onFold={() => undefined} />);
    expect(document.querySelector("rect")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
