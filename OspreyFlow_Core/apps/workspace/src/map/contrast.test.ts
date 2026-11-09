import { describe, expect, it } from "vitest";

import { contrastRatio } from "./contrast";

describe("contrastRatio", () => {
  it("is WCAG's ratio, unrounded", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 10);
    expect(contrastRatio("#767676", "#ffffff")).toBeGreaterThan(4.5); // the classic 4.54:1 grey
    // #777777 on white is 4.478…: rounded to two places it would read 4.48, and a 4.5 floor must
    // see it under, as an exact comparison does.
    expect(contrastRatio("#777777", "#ffffff")).toBeLessThan(4.5);
    expect(contrastRatio("rgb(0, 0, 0)", "#ffffff")).toBeCloseTo(21, 10);
  });

  it("refuses a colour with an alpha channel rather than reading it as opaque", () => {
    expect(() => contrastRatio("rgba(0, 0, 0, 0.5)", "#ffffff")).toThrow("opaque colours only");
    expect(() => contrastRatio("#00000080", "#ffffff")).toThrow("opaque colours only");
  });
});
