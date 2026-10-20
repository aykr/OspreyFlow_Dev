import { afterEach, describe, expect, it, vi } from "vitest";

import { bandChangeTouchesLinks, redrawOnBandChange, redrawWhenCameraStops } from "./cameraMoves";

afterEach(() => vi.unstubAllGlobals());

describe("redrawWhenCameraStops", () => {
  it("draws the canvas again after the move has finished, and not before", async () => {
    vi.stubGlobal("requestAnimationFrame", (callback: () => void) => {
      callback();
      return 0;
    });
    const refresh = vi.fn();
    let finish: () => void = () => undefined;
    redrawWhenCameraStops({ refresh }, new Promise<void>((resolve) => (finish = resolve)));
    expect(refresh).not.toHaveBeenCalled();
    finish();
    await Promise.resolve();
    await Promise.resolve();
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});

describe("redrawOnBandChange", () => {
  function renderer(size = 1) {
    const refresh = vi.fn();
    return { refresh, getGraph: () => ({ nodes: () => ["a", "b"], edges: () => ["e"], size }) };
  }

  // ADR-115 Amendment 1: a node's icon appears from the neighbourhood band in. The renderer reruns
  // its reducers only when asked, and a wheel zoom does not ask, so crossing a band must.
  it("draws again when the zoom crosses into another band, and not while it stays in one", () => {
    const sigma = renderer();
    const onBand = redrawOnBandChange(sigma, 1);
    onBand({ ratio: 0.9 });
    onBand({ ratio: 0.5 });
    expect(sigma.refresh).not.toHaveBeenCalled();
    onBand({ ratio: 0.3 });
    expect(sigma.refresh).toHaveBeenCalledTimes(1);
    onBand({ ratio: 0.25 });
    expect(sigma.refresh).toHaveBeenCalledTimes(1);
    onBand({ ratio: 1 });
    expect(sigma.refresh).toHaveBeenCalledTimes(2);
  });

  // ADR-118: a whole refresh held a 50k/250k graph for two seconds. A band moves nothing, and links
  // look different only in the overview and link-detail bands.
  it("works out the nodes again on every band change, the links only where they look different, and indexes nothing", () => {
    const sigma = renderer();
    const onBand = redrawOnBandChange(sigma, 1);
    const at = (ratio: number) => {
      sigma.refresh.mockClear();
      onBand({ ratio });
      return sigma.refresh.mock.calls[0]?.[0];
    };
    // Starting in the structure band (ratio 1): into neighbourhood, then overview, then link detail.
    const middle = at(0.3);
    expect(middle).toEqual({ partialGraph: { nodes: ["a", "b"] }, skipIndexation: true });
    const overview = at(2);
    expect(overview).toEqual({ partialGraph: { nodes: ["a", "b"], edges: ["e"] }, skipIndexation: true });
    const close = at(0.1);
    expect(close).toEqual({ partialGraph: { nodes: ["a", "b"], edges: ["e"] }, skipIndexation: true });
  });

  // ADR-119 under Sigma 4: on a large working set the links between communities give way to every
  // link from the neighbourhood band in, so that change touches every link too; refreshing only the
  // nodes there left every individual link hidden once zoomed in (20 October 2026, the rebase).
  it("works out the links again where a large working set's links between communities give way to every link", () => {
    const sigma = renderer(20_000);
    const onBand = redrawOnBandChange(sigma, 1);
    onBand({ ratio: 0.3 });
    expect(sigma.refresh).toHaveBeenCalledWith({ partialGraph: { nodes: ["a", "b"], edges: ["e"] }, skipIndexation: true });
  });
});

describe("bandChangeTouchesLinks", () => {
  it("is true only where the overview or the link-detail band is involved", () => {
    expect(bandChangeTouchesLinks("structure", "neighbourhood")).toBe(false);
    expect(bandChangeTouchesLinks("neighbourhood", "structure")).toBe(false);
    expect(bandChangeTouchesLinks("structure", "overview")).toBe(true);
    expect(bandChangeTouchesLinks("overview", "structure")).toBe(true);
    expect(bandChangeTouchesLinks("neighbourhood", "link-detail")).toBe(true);
    expect(bandChangeTouchesLinks("link-detail", "neighbourhood")).toBe(true);
  });
});
