import { describe, expect, it } from "vitest";

import { pointInPolygon } from "./geometry";

const UNIT_SQUARE = [
  { x: 0, y: 0 },
  { x: 10, y: 0 },
  { x: 10, y: 10 },
  { x: 0, y: 10 },
];

describe("pointInPolygon", () => {
  it("is true for a point well inside the polygon", () => {
    expect(pointInPolygon({ x: 5, y: 5 }, UNIT_SQUARE)).toBe(true);
  });

  it("is false for a point well outside the polygon", () => {
    expect(pointInPolygon({ x: 20, y: 20 }, UNIT_SQUARE)).toBe(false);
  });

  it("works unchanged for lon/lat-shaped coordinates, not just screen pixels", () => {
    const boundary = [
      { x: -1.5, y: 51.4 },
      { x: -1.4, y: 51.4 },
      { x: -1.4, y: 51.5 },
      { x: -1.5, y: 51.5 },
    ];
    expect(pointInPolygon({ x: -1.45, y: 51.45 }, boundary)).toBe(true);
    expect(pointInPolygon({ x: -1.6, y: 51.45 }, boundary)).toBe(false);
  });
});
