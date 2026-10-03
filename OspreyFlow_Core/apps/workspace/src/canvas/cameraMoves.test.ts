import { afterEach, describe, expect, it, vi } from "vitest";

import { redrawWhenCameraStops } from "./cameraMoves";

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
