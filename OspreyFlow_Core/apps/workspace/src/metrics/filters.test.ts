import { describe, expect, it } from "vitest";

import { NO_FILTER, filterDimming, valueRange, type FilterEdge, type MetricFilter } from "./filters";

// ADR-088. Two social-network filters, both of which dim and never remove (spec 02 §2 rule 2): a
// relationship-strength floor that dims weak links and the nodes left with no strong link, and a
// metric threshold that dims nodes below a value of the chosen metric.

const nodes = ["a", "b", "c", "d"];
const edges: FilterEdge[] = [
  { id: "ab", source: "a", target: "b", weight: 0.9 },
  { id: "bc", source: "b", target: "c", weight: 0.2 },
  { id: "cd", source: "c", target: "d", weight: 0.1 },
];

describe("filterDimming", () => {
  it("dims nothing with no filter", () => {
    const result = filterDimming(nodes, edges, NO_FILTER);
    expect(result.dimmedNodeIds.size).toBe(0);
    expect(result.dimmedEdgeIds.size).toBe(0);
  });

  it("dims links below the strength floor, and the nodes left with no strong link", () => {
    const result = filterDimming(nodes, edges, { ...NO_FILTER, strengthFloor: 0.5 });
    expect(result.dimmedEdgeIds).toEqual(new Set(["bc", "cd"]));
    // a and b keep their strong link; c and d have none left.
    expect(result.dimmedNodeIds).toEqual(new Set(["c", "d"]));
  });

  it("leaves a node with no links at all alone under the strength floor", () => {
    const result = filterDimming(["a", "b", "lone"], edges.slice(0, 1), { ...NO_FILTER, strengthFloor: 0.5 });
    expect(result.dimmedNodeIds.size).toBe(0);
  });

  it("dims nodes below the metric threshold, and a node the metric has no value for", () => {
    const filter: MetricFilter = {
      ...NO_FILTER,
      metric: "clique_metric",
      threshold: 0.5,
      values: { a: 0.9, b: 0.5, c: 0.1 },
    };
    const result = filterDimming(nodes, edges, filter);
    expect(result.dimmedNodeIds).toEqual(new Set(["c", "d"]));
    expect(result.dimmedEdgeIds.size).toBe(0);
  });

  it("applies both filters at once, each adding to what is dimmed", () => {
    const filter: MetricFilter = {
      strengthFloor: 0.5,
      metric: "degree",
      threshold: 1,
      values: { a: 2, b: 0, c: 2, d: 1 },
    };
    const result = filterDimming(nodes, edges, filter);
    expect(result.dimmedNodeIds).toEqual(new Set(["b", "c", "d"]));
    expect(result.dimmedEdgeIds).toEqual(new Set(["bc", "cd"]));
  });

  it("a metric chosen but not yet valued dims nothing", () => {
    const result = filterDimming(nodes, edges, { ...NO_FILTER, metric: "degree", threshold: 1, values: null });
    expect(result.dimmedNodeIds.size).toBe(0);
  });
});

describe("valueRange", () => {
  it("gives the smallest and largest value, and a unit range for nothing", () => {
    expect(valueRange({ a: 0.2, b: 0.9, c: 0.5 })).toEqual({ min: 0.2, max: 0.9 });
    expect(valueRange({})).toEqual({ min: 0, max: 1 });
    expect(valueRange(null)).toEqual({ min: 0, max: 1 });
  });
});

// ADR-139 decision 6: connection strength is a link metric. A link below the threshold dims, and a
// node whose strongest link is below it dims, exactly as the metric filter dims a node.
describe("filterDimming by connection strength", () => {
  it("dims each link below the threshold and the nodes none of whose links reach it", () => {
    const filter: MetricFilter = {
      ...NO_FILTER,
      metric: "connection_strength",
      threshold: 0.5,
      values: { a: 0.9, b: 0.9, c: 0.3, d: 0.1 },
      edgeValues: { ab: 0.9, bc: 0.3, cd: 0.1 },
    };
    const result = filterDimming(nodes, edges, filter);
    expect(result.dimmedEdgeIds).toEqual(new Set(["bc", "cd"]));
    expect(result.dimmedNodeIds).toEqual(new Set(["c", "d"]));
  });

  it("dims a link it has no strength for, as a node the metric gave no value is dimmed", () => {
    const filter: MetricFilter = {
      ...NO_FILTER,
      metric: "connection_strength",
      threshold: 0.2,
      values: { a: 0.9, b: 0.9 },
      edgeValues: { ab: 0.9 },
    };
    expect(filterDimming(nodes, edges, filter).dimmedEdgeIds).toEqual(new Set(["bc", "cd"]));
  });

  it("dims nodes below a shared-attribute rarity, and leaves the links to the node rule", () => {
    const filter: MetricFilter = {
      ...NO_FILTER,
      metric: "shared_attribute_rarity",
      threshold: 1,
      values: { a: 2.3, b: 0.4 },
      edgeValues: null,
    };
    const result = filterDimming(nodes, edges, filter);
    expect(result.dimmedNodeIds).toEqual(new Set(["b", "c", "d"]));
    expect(result.dimmedEdgeIds.size).toBe(0);
  });
});
