import { describe, expect, it } from "vitest";

import { emergence, type FirstSeen } from "./emergence";

// ADR-087. The timeline's playback lights a node or a link up at its first event inside the brush
// window and keeps it lit; everything with no event in the window stays dimmed throughout.

const firstSeen: FirstSeen = {
  nodes: { a: "2026-01-01T09:00:00Z", b: "2026-01-01T09:00:00Z", c: "2026-01-01T11:00:00Z" },
  edges: { ab: "2026-01-01T09:00:00Z", bc: "2026-01-01T11:00:00Z" },
};
const nodes = ["a", "b", "c", "d"];
const edges = ["ab", "bc", "cd"];

describe("emergence", () => {
  it("with no playhead, dims only what has no event in the window", () => {
    const result = emergence(firstSeen, null, nodes, edges);
    expect(result.dimmedNodeIds).toEqual(new Set(["d"]));
    expect(result.dimmedEdgeIds).toEqual(new Set(["cd"]));
  });

  it("before anything has happened, dims everything", () => {
    const result = emergence(firstSeen, new Date("2026-01-01T08:00:00Z"), nodes, edges);
    expect(result.dimmedNodeIds).toEqual(new Set(nodes));
    expect(result.dimmedEdgeIds).toEqual(new Set(edges));
  });

  it("lights a node or link up as the playhead passes its first event, and keeps it lit", () => {
    const at10 = emergence(firstSeen, new Date("2026-01-01T10:00:00Z"), nodes, edges);
    expect(at10.dimmedNodeIds).toEqual(new Set(["c", "d"]));
    expect(at10.dimmedEdgeIds).toEqual(new Set(["bc", "cd"]));
    const at11 = emergence(firstSeen, new Date("2026-01-01T11:00:00Z"), nodes, edges);
    expect(at11.dimmedNodeIds).toEqual(new Set(["d"]));
    expect(at11.dimmedEdgeIds).toEqual(new Set(["cd"]));
  });

  it("with nothing known, dims nothing when there is no filter and everything when there is", () => {
    const none: FirstSeen = { nodes: {}, edges: {} };
    expect(emergence(null, null, nodes, edges).dimmedNodeIds.size).toBe(0);
    expect(emergence(none, null, nodes, edges).dimmedNodeIds).toEqual(new Set(nodes));
    expect(emergence(none, null, nodes, edges).dimmedEdgeIds).toEqual(new Set(edges));
  });
});
