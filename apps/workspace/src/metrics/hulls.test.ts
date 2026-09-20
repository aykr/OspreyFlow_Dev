import { describe, expect, it } from "vitest";

import { makeNode } from "../testing/fixtures";
import { createWorkingSet } from "../workingset/store";
import { computeCommunityHulls } from "./hulls";

function graphWithPositions(positions: Record<string, [number, number]>) {
  const { graph } = createWorkingSet();
  for (const id of Object.keys(positions)) {
    graph.addNode(id, { data: makeNode(id), x: 0, y: 0 });
  }
  for (const [id, [x, y]] of Object.entries(positions)) {
    graph.mergeNodeAttributes(id, { x, y });
  }
  return graph;
}

describe("computeCommunityHulls", () => {
  it("returns a hull polygon for a community with three or more members", () => {
    const graph = graphWithPositions({
      a: [0, 0],
      b: [10, 0],
      c: [10, 10],
      d: [0, 10],
    });

    const hulls = computeCommunityHulls(graph, { a: "0", b: "0", c: "0", d: "0" });

    expect(hulls.size).toBe(1);
    const hull = hulls.get("0");
    expect(hull).toBeDefined();
    expect(hull!.length).toBeGreaterThanOrEqual(3);
  });

  it("omits a community with fewer than three distinct positions rather than a degenerate shape", () => {
    const graph = graphWithPositions({ a: [0, 0], b: [10, 0] });

    const hulls = computeCommunityHulls(graph, { a: "0", b: "0" });

    expect(hulls.has("0")).toBe(false);
  });

  it("keeps two communities' hulls independent", () => {
    const graph = graphWithPositions({
      a: [0, 0],
      b: [1, 0],
      c: [0, 1],
      x: [100, 100],
      y: [101, 100],
      z: [100, 101],
    });

    const hulls = computeCommunityHulls(graph, {
      a: "left",
      b: "left",
      c: "left",
      x: "right",
      y: "right",
      z: "right",
    });

    expect(hulls.size).toBe(2);
    expect(hulls.get("left")).toBeDefined();
    expect(hulls.get("right")).toBeDefined();
  });

  it("ignores a community entry for a node no longer in the working set", () => {
    const graph = graphWithPositions({ a: [0, 0], b: [1, 0], c: [0, 1] });

    const hulls = computeCommunityHulls(graph, {
      a: "0",
      b: "0",
      c: "0",
      "not-in-graph": "0",
    });

    expect(hulls.get("0")?.length).toBeGreaterThanOrEqual(3);
  });
});
