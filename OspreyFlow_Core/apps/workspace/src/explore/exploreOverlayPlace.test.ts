// The empty canvas's "Where to start" panel and the welcome panel must not overlap.
import { describe, expect, it } from "vitest";

import { exploreOverlayPlace } from "./exploreOverlayPlace";

/** Lays the two panels out on a canvas `canvas` px wide, as the browser would (welcome 320 + 8). */
function geometry(canvas: number, welcomeOpen: boolean): { left: number; right: number } {
  const room = 320 + 8;
  const place = exploreOverlayPlace(welcomeOpen);
  const centre = welcomeOpen ? canvas / 2 + room / 2 : canvas / 2;
  const width = Math.min(448, welcomeOpen ? canvas - room - 32 : canvas - 32);
  expect(String(place.left)).toContain(welcomeOpen ? "var(--w-welcome-panel)" : "50%");
  return { left: centre - width / 2, right: centre + width / 2 };
}

describe("the empty canvas's 'Where to start' panel", () => {
  it("clears the welcome panel at the widths the Glass is used at", () => {
    for (const canvas of [760, 1052, 1400, 1900]) {
      const { left, right } = geometry(canvas, true);
      expect(left, `canvas ${canvas}px`).toBeGreaterThanOrEqual(328);
      expect(right, `canvas ${canvas}px`).toBeLessThanOrEqual(canvas);
    }
  });

  it("is centred on the canvas when the welcome panel is closed", () => {
    expect(exploreOverlayPlace(false)).toEqual({ left: "50%", width: "min(28rem, calc(100% - var(--sp-32)))" });
  });
});
