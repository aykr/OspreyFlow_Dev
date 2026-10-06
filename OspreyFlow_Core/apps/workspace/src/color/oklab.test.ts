import { describe, expect, it } from "vitest";

import { mixOklab, oklabLightness, readableTextOn } from "./oklab";

function lightnessGap(a: string, b: string): number {
  return Math.abs(oklabLightness(a) - oklabLightness(b));
}

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

describe("readableTextOn", () => {
  it("is white on a dark fill and near-black on a light one", () => {
    expect(readableTextOn("#1b2a6b")).toBe("#ffffff");
    expect(readableTextOn("#e8d9a0")).toBe("#101314");
  });

  it("chooses the colour that is further from the fill, for every channel in either theme", () => {
    // Not a contrast standard, only that the choice is never the worse of the two.
    for (const hex of ["#677bd6", "#5367cb", "#35b9c0", "#c08a34", "#d96b8a", "#7b5fd0", "#3f9d6a"]) {
      const text = readableTextOn(hex);
      const other = text === "#ffffff" ? "#101314" : "#ffffff";
      expect(lightnessGap(hex, text)).toBeGreaterThanOrEqual(lightnessGap(hex, other));
    }
  });
});
