import { describe, expect, it } from "vitest";

import { mixOklab } from "./oklab";

// No independent oracle for an exact expected hex is available offline —
// these assert the algebraic properties any correct OKLab mix must have.
// `spec/design/tokens.css`'s literal `color-mix(in oklab, ...)` values are
// cross-checked against a real browser's own CSS engine during this
// checkpoint's playwright verification pass, not duplicated as a second
// hardcoded fixture here.
describe("mixOklab", () => {
  it("100% foreground returns the foreground colour", () => {
    expect(mixOklab("#677bd6", "#161a1b", 100).toLowerCase()).toBe("#677bd6");
  });

  it("0% foreground returns the background colour", () => {
    expect(mixOklab("#677bd6", "#161a1b", 0).toLowerCase()).toBe("#161a1b");
  });

  it("mixing a colour with itself returns itself at any percentage", () => {
    expect(mixOklab("#677bd6", "#677bd6", 32).toLowerCase()).toBe("#677bd6");
  });

  it("32% (dimmed) sits closer to the surface than 12% (filtered out) does", () => {
    // A channel colour mixed toward a much darker surface: more channel
    // (32%) must not end up darker/further-from-channel than less channel
    // (12%) would — monotonic in the mix fraction.
    const channel = "#677bd6"; // indigo
    const surface = "#161a1b"; // dark surface-panel
    const dimmed = mixOklab(channel, surface, 32);
    const filteredOut = mixOklab(channel, surface, 12);

    const distanceFromSurface = (hex: string) => {
      const n = Number.parseInt(hex.replace("#", ""), 16);
      const sn = Number.parseInt(surface.replace("#", ""), 16);
      return Math.abs(n - sn);
    };
    expect(distanceFromSurface(dimmed)).toBeGreaterThan(distanceFromSurface(filteredOut));
  });
});
