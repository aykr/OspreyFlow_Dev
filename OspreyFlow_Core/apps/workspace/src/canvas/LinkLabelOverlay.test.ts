import { describe, expect, it } from "vitest";

import { placeLinkLabel } from "./LinkLabelOverlay";

// Sigma 4 draws a link's label from its source to its target, so a link pointing left read upside
// down. The overlay turns it so it always reads left to right, and keeps it off the line.
describe("placeLinkLabel", () => {
  it("lays a label along a link pointing right, above its middle", () => {
    const at = placeLinkLabel({ x: 0, y: 100 }, { x: 200, y: 100 }, 2);
    expect(at.angle).toBe(0);
    expect(at.x).toBe(100);
    expect(at.y).toBeLessThan(100);
  });

  it("turns a label on a link pointing left, so it is not upside down", () => {
    const at = placeLinkLabel({ x: 200, y: 100 }, { x: 0, y: 100 }, 2);
    expect(Math.abs(at.angle)).toBeCloseTo(0);
    expect(at.y).toBeLessThan(100);
  });

  it("keeps every angle between -90 and 90 degrees", () => {
    for (let turn = 0; turn < 360; turn += 15) {
      const r = (turn * Math.PI) / 180;
      const { angle } = placeLinkLabel({ x: 0, y: 0 }, { x: Math.cos(r) * 100, y: Math.sin(r) * 100 }, 2);
      expect(angle).toBeGreaterThanOrEqual(-90);
      expect(angle).toBeLessThanOrEqual(90);
    }
  });

  it("is the same for a link and its reverse", () => {
    const a = { x: 10, y: 20 };
    const b = { x: 140, y: 90 };
    const forward = placeLinkLabel(a, b, 2);
    const reverse = placeLinkLabel(b, a, 2);
    expect(reverse.angle).toBeCloseTo(forward.angle);
    expect(reverse.x).toBeCloseTo(forward.x);
    expect(reverse.y).toBeCloseTo(forward.y);
  });
});
