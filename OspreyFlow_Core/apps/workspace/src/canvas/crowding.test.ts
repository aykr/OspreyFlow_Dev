// A crowded view is quieter: with a few hundred nodes and links on screen the nodes are drawn
// smaller and the links thinner, so the structure shows through instead of a mass of ink. The
// scale depends only on how many there are, never on what they are (spec 02 §4: colour is entity
// type, and zoom never changes what exists).
import { describe, expect, it } from "vitest";

import { makeEdge, makeNode } from "../testing/fixtures";
import { computeEdgeAttributes, computeNodeFrameAttributes, crowdingScale } from "./nodeAttributes";

describe("crowdingScale", () => {
  it("leaves a small view at full size", () => {
    expect(crowdingScale(0)).toBe(1);
    expect(crowdingScale(40)).toBe(1);
    expect(crowdingScale(150)).toBe(1);
    expect(crowdingScale(undefined)).toBe(1);
  });

  it("shrinks steadily as the view fills, and never below the floor", () => {
    const sizes = [150, 400, 1000, 3000, 20000].map((n) => crowdingScale(n));
    sizes.slice(1).forEach((size, i) => expect(size).toBeLessThanOrEqual(sizes[i] ?? 1));
    expect(crowdingScale(400)).toBeLessThan(1);
    expect(crowdingScale(3000)).toBeCloseTo(0.55, 5);
    expect(crowdingScale(20000)).toBeCloseTo(0.55, 5);
  });
});

describe("a crowded view draws smaller nodes and thinner links", () => {
  it("a node in a view of 2,000 nodes is smaller than the same node in a view of 20, and still visible", () => {
    const at = { cameraRatio: 0.3, degree: 3 };
    const sparse = computeNodeFrameAttributes(makeNode("n1"), { ...at, viewNodeCount: 20 });
    const crowded = computeNodeFrameAttributes(makeNode("n1"), { ...at, viewNodeCount: 2000 });
    expect(crowded.size).toBeLessThan(sparse.size);
    expect(crowded.size).toBeGreaterThanOrEqual(2);
  });

  it("without a count, a node is drawn as before", () => {
    const at = { cameraRatio: 0.3, degree: 3 };
    expect(computeNodeFrameAttributes(makeNode("n1"), at).size).toBe(
      computeNodeFrameAttributes(makeNode("n1"), { ...at, viewNodeCount: 20 }).size,
    );
  });

  it("a link in a view of 5,000 links is thinner than in a view of 20, and still drawn", () => {
    const edge = makeEdge("e1", "a", "b", { weight: 2 });
    const base = { cameraRatio: 0.3, strengthFilterFloor: 0, onPath: false };
    const sparse = computeEdgeAttributes(edge, { ...base, viewEdgeCount: 20 });
    const crowded = computeEdgeAttributes(edge, { ...base, viewEdgeCount: 5000 });
    expect(crowded.size).toBeLessThan(sparse.size);
    expect(crowded.size).toBeGreaterThanOrEqual(0.5);
    expect(crowded.hidden).toBe(false);
  });

  it("a link on a found path stays as thick as ever however crowded the view", () => {
    const edge = makeEdge("e1", "a", "b", { weight: 1 });
    const base = { cameraRatio: 0.3, strengthFilterFloor: 0, onPath: true };
    expect(computeEdgeAttributes(edge, { ...base, viewEdgeCount: 5000 }).size).toBe(
      computeEdgeAttributes(edge, { ...base, viewEdgeCount: 20 }).size,
    );
  });
});
