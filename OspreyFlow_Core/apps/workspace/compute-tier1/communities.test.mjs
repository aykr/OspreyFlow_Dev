// `splitDisconnectedCommunities` — `06_DECISIONS.md` ADR-029's own connected-components fix,
// this tier's own copy. Mirrors `tests/adapters/compute_rustworkx/test_communities.py` exactly —
// same three cases, same adversarial partition — because ADR-029 requires the fix "written and
// run in both languages against the same adversarial input, since the fix itself is duplicated,
// not shared." See that file's own docstring for why this bypasses Louvain entirely rather than
// seeding a graph and hoping it reproduces the disconnection bug: `graphology-communities-louvain`
// already separates two disjoint edges into two communities on a trivial graph with nothing else
// in it, so a conformance-level test feeding only such a graph through the real adapter would
// pass identically whether or not this split pass exists at all.
import { describe, expect, it } from "vitest";

import { splitDisconnectedCommunities } from "./communities.mjs";

describe("splitDisconnectedCommunities", () => {
  it("separates unconnected members sharing one label", () => {
    const nodeIds = ["a", "b", "c", "d"];
    const edges = [
      ["a", "b"],
      ["c", "d"],
    ];
    // Deliberately wrong: both pairs share one label, as an upstream Louvain call could in
    // principle produce, even though {a, b} and {c, d} share no edge at all.
    const wrongPartition = { a: 0, b: 0, c: 0, d: 0 };

    const result = splitDisconnectedCommunities(nodeIds, edges, wrongPartition);

    expect(result.a).toBe(result.b);
    expect(result.c).toBe(result.d);
    expect(result.a).not.toBe(result.c);
  });

  it("leaves a genuinely connected group alone", () => {
    const nodeIds = ["a", "b", "c"];
    const edges = [
      ["a", "b"],
      ["b", "c"],
    ];
    const partition = { a: 0, b: 0, c: 0 };

    const result = splitDisconnectedCommunities(nodeIds, edges, partition);

    expect(result.a).toBe(result.b);
    expect(result.b).toBe(result.c);
  });

  it("keeps a true singleton as its own group", () => {
    const nodeIds = ["a", "b", "isolated"];
    const edges = [["a", "b"]];
    const partition = { a: 0, b: 0, isolated: 1 };

    const result = splitDisconnectedCommunities(nodeIds, edges, partition);

    expect(result.a).toBe(result.b);
    expect(result.isolated).not.toBe(result.a);
  });
});
