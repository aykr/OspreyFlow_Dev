import { afterEach, describe, expect, it, vi } from "vitest";

import { redrawOnBandChange, redrawWhenCameraStops } from "./cameraMoves";

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
  // ADR-115 Amendment 1: a node's icon appears from the neighbourhood band in. The renderer reruns
  // its reducers only when asked, and a wheel zoom does not ask, so crossing a band must.
  it("draws again when the zoom crosses into another band, and not while it stays in one", () => {
    const refresh = vi.fn();
    const onBand = redrawOnBandChange({ refresh }, 1);
    onBand({ ratio: 0.9 });
    onBand({ ratio: 0.5 });
    expect(refresh).not.toHaveBeenCalled();
    onBand({ ratio: 0.3 });
    expect(refresh).toHaveBeenCalledTimes(1);
    onBand({ ratio: 0.25 });
    expect(refresh).toHaveBeenCalledTimes(1);
    onBand({ ratio: 1 });
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
