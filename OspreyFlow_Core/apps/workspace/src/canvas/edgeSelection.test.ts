import { describe, expect, it } from "vitest";

import { EDGE_HIT_PX, nearestEdge, nextLink, type ScreenSegment } from "./edgeSelection";

const seg = (id: string, ax: number, ay: number, bx: number, by: number): ScreenSegment => ({ id, ax, ay, bx, by });

describe("nearestEdge", () => {
  const flat = [seg("flat", 0, 0, 100, 0)];

  it("finds a link the pointer is on", () => {
    expect(nearestEdge(50, 0, flat)).toBe("flat");
  });

  it("finds a link a few pixels off the drawn line, which is what makes a thin line clickable", () => {
    expect(nearestEdge(50, EDGE_HIT_PX - 0.5, flat)).toBe("flat");
    expect(nearestEdge(50, -(EDGE_HIT_PX - 0.5), flat)).toBe("flat");
  });

  it("finds nothing beyond that distance", () => {
    expect(nearestEdge(50, EDGE_HIT_PX + 1, flat)).toBeNull();
  });

  it("measures to the end of the segment, not to the line it lies on", () => {
    expect(nearestEdge(100 + EDGE_HIT_PX + 4, 0, flat)).toBeNull();
    expect(nearestEdge(100 + 3, 0, flat)).toBe("flat");
    expect(nearestEdge(-3, 0, flat)).toBe("flat");
  });

  it("works on a slanted link", () => {
    const slant = [seg("s", 0, 0, 100, 100)];
    expect(nearestEdge(50, 54, slant)).toBe("s"); // about 2.8px off the diagonal
    expect(nearestEdge(50, 70, slant)).toBeNull(); // about 14px off
  });

  it("picks the nearer of two links", () => {
    const two = [seg("far", 0, 5, 100, 5), seg("near", 0, 1, 100, 1)];
    expect(nearestEdge(50, 0, two)).toBe("near");
  });

  it("copes with a link whose ends are the same point", () => {
    expect(nearestEdge(2, 2, [seg("dot", 0, 0, 0, 0)])).toBe("dot");
    expect(nearestEdge(50, 50, [seg("dot", 0, 0, 0, 0)])).toBeNull();
  });

  it("finds nothing when there are no links", () => {
    expect(nearestEdge(0, 0, [])).toBeNull();
  });

  it("takes a different reach when asked", () => {
    expect(nearestEdge(50, 10, flat, 12)).toBe("flat");
  });
});

describe("nextLink", () => {
  const ids = ["e3", "e1", "e2"];

  it("starts at the first link, in a stable order, when none is selected", () => {
    expect(nextLink(ids, null, 1)).toBe("e1");
  });

  it("starts at the last link going backwards", () => {
    expect(nextLink(ids, null, -1)).toBe("e3");
  });

  it("moves on, and wraps round", () => {
    expect(nextLink(ids, "e1", 1)).toBe("e2");
    expect(nextLink(ids, "e3", 1)).toBe("e1");
    expect(nextLink(ids, "e1", -1)).toBe("e3");
  });

  it("starts again when the selected link belongs to another node", () => {
    expect(nextLink(ids, "elsewhere", 1)).toBe("e1");
  });

  it("returns nothing for a node with no links", () => {
    expect(nextLink([], null, 1)).toBeNull();
  });
});
