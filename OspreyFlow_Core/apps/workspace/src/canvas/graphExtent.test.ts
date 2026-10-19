import Graph from "graphology";
import { describe, expect, it } from "vitest";

import { graphExtent } from "./graphExtent";

describe("graphExtent", () => {
  it("is the smallest and largest position of the nodes on each axis", () => {
    const graph = new Graph();
    graph.addNode("a", { x: -3, y: 10 });
    graph.addNode("b", { x: 7, y: -2 });
    graph.addNode("c", { x: 1, y: 4 });
    expect(graphExtent(graph)).toEqual({ x: [-3, 7], y: [-2, 10] });
  });

  it("counts a node with no position at the origin", () => {
    const graph = new Graph();
    graph.addNode("a", { x: 5, y: 5 });
    graph.addNode("b");
    expect(graphExtent(graph)).toEqual({ x: [0, 5], y: [0, 5] });
  });
});
