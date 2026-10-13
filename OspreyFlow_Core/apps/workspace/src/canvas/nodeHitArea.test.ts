// DESIGN.md v0.3 §5a: every node has a 24×24 hit area (WCAG 2.2 SC 2.5.8), though drawn 14px across.
// A click the renderer did not place on a node is checked against each node's centre: within 12px,
// it is a click on the nearest such node.
import { describe, expect, it } from "vitest";

import { HIT_RADIUS, nodeWithinReach } from "./nodeHitArea";

const at = (id: string, x: number, y: number, size = 7) => ({ id, x, y, size });

describe("a node's hit area", () => {
  it("reaches 12px from the centre, beyond the 7px it is drawn", () => {
    expect(HIT_RADIUS).toBe(12);
    expect(nodeWithinReach([at("a", 100, 100)], 111, 100)).toBe("a");
    expect(nodeWithinReach([at("a", 100, 100)], 100, 112)).toBe("a");
    expect(nodeWithinReach([at("a", 100, 100)], 113, 100)).toBeNull();
  });

  it("chooses the nearest of two nodes in reach", () => {
    expect(nodeWithinReach([at("a", 100, 100), at("b", 118, 100)], 110, 100)).toBe("b");
  });

  it("a node drawn larger than the hit area is reached across its own size", () => {
    expect(nodeWithinReach([at("big", 100, 100, 20)], 119, 100)).toBe("big");
  });

  it("between two nodes drawn in one place, takes the one drawn on top (the later), as the renderer does", () => {
    const stacked = [
      { id: "under", x: 100, y: 100, size: 7 },
      { id: "over", x: 100, y: 100, size: 7 },
    ];
    expect(nodeWithinReach(stacked, 108, 106)).toBe("over");
  });
});
