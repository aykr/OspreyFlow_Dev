// DESIGN.md v0.3 §3.8 and §5a (ADR-115 E1): inferred links are dashed `4 3` and unresolved links dotted
// `1 3`, on edges as in the legend. The canvas draws each doubled (ADR-097 step 2: a one- or two-pixel
// gap reads as a solid line once rasterised), so the ratio is the contract's and the size twice it.
import { describe, expect, it } from "vitest";

import { DASH_LENGTH_PX, DASH_PERIOD_PX, DOT_LENGTH_PX, DOT_PERIOD_PX } from "./provenancePatterns";

describe("a link's provenance pattern", () => {
  it("inferred is DESIGN.md's 4 3, doubled", () => {
    expect([DASH_LENGTH_PX, DASH_PERIOD_PX - DASH_LENGTH_PX]).toEqual([8, 6]);
  });

  it("unresolved is DESIGN.md's 1 3, doubled", () => {
    expect([DOT_LENGTH_PX, DOT_PERIOD_PX - DOT_LENGTH_PX]).toEqual([2, 6]);
  });
});
