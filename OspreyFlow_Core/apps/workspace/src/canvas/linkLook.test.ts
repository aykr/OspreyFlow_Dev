import { describe, expect, it } from "vitest";

import { linkLookFor, MIN_PATTERNED_SIZE, PATTERN_BASE_WIDTH } from "./linkLook";
import { DASH_LENGTH_PX, DASH_PERIOD_PX, DOT_LENGTH_PX, DOT_PERIOD_PX } from "./provenancePatterns";

// ADR-081 and ADR-097 step 2: a link's line follows its provenance and basis, and an arrowhead shows
// only for a directed type. Under Sigma 4 the style is values the one link program reads.
describe("linkLookFor", () => {
  it("draws a plain link solid, a pixel wide, with no arrowhead", () => {
    expect(linkLookFor("glass-edge", "#888888", 0.5)).toEqual({
      plainColor: "#888888",
      dashLength: 0,
      dashGap: 0,
      head: undefined,
      size: 1,
    });
  });

  it("draws a directed link solid with an arrowhead, never narrower than Sigma 3 drew it", () => {
    const look = linkLookFor("glass-arrow", "#888888", 1);
    expect(look.head).toBe("arrow");
    expect(look.dashGap).toBe(0);
    // Sigma 3 drew these twice their size wide; Sigma 4 draws the size as the whole width.
    expect(look.size).toBe(2 * MIN_PATTERNED_SIZE);
    expect(linkLookFor("glass-arrow", "#888888", 4).size).toBe(8);
  });

  it("draws a thick link at its own width", () => {
    expect(linkLookFor("glass-edge-thick", "#888888", 3).size).toBe(6);
  });

  it("draws an unresolved or probabilistic link dotted and an inferred one dashed, with no solid line under", () => {
    for (const program of ["glass-edge-dotted", "glass-arrow-dotted"] as const) {
      const look = linkLookFor(program, "#888888", 1);
      // As multiples of the width: the Sigma 3 pixels at the narrowest width, so DESIGN.md's 1 3.
      expect([look.dashLength * PATTERN_BASE_WIDTH, look.dashGap * PATTERN_BASE_WIDTH]).toEqual([
        DOT_LENGTH_PX,
        DOT_PERIOD_PX - DOT_LENGTH_PX,
      ]);
      expect(look.plainColor).toBe("transparent");
    }
    for (const program of ["glass-edge-dashed", "glass-arrow-dashed"] as const) {
      const look = linkLookFor(program, "#888888", 1);
      expect(look.dashLength * PATTERN_BASE_WIDTH).toBeCloseTo(DASH_LENGTH_PX);
      expect(look.dashGap * PATTERN_BASE_WIDTH).toBeCloseTo(DASH_PERIOD_PX - DASH_LENGTH_PX);
      expect(look.plainColor).toBe("transparent");
    }
    expect(linkLookFor("glass-arrow-dotted", "#888888", 1).head).toBe("arrow");
    expect(linkLookFor("glass-edge-dashed", "#888888", 1).head).toBeUndefined();
  });
});
