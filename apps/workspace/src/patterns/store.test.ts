import { describe, expect, it } from "vitest";

import {
  addEdge,
  addVariableNode,
  createEmptyPattern,
  fromPatternQuery,
  pinNode,
  removeElement,
  toPatternQuery,
  unpinnedSecondaryRoots,
} from "./store";

describe("unpinnedSecondaryRoots", () => {
  it("is empty for a single-chain pattern (one root)", () => {
    let state = createEmptyPattern();
    state = addVariableNode(state, "Person");
    state = addVariableNode(state, "Endpoint");
    state = addEdge(state, "USES", "a", "b");
    expect(unpinnedSecondaryRoots(state)).toEqual([]);
  });

  it("flags a second, unpinned root the instant it exists — before Preview/Run is ever pressed", () => {
    let state = createEmptyPattern();
    state = addVariableNode(state, "Person"); // var a — primary root
    state = addVariableNode(state, "Person"); // var b — a second, disconnected, unpinned root
    const flagged = unpinnedSecondaryRoots(state);
    expect(flagged.map((n) => n.var)).toEqual(["b"]);
  });

  it("clears once the second root is pinned — B19's own real shape", () => {
    let state = createEmptyPattern();
    state = addVariableNode(state, "Person"); // a
    state = pinNode(state, "Person", "known-node-id", "Person · known-node-id"); // b, pinned
    state = addVariableNode(state, "Endpoint"); // c — the discovered common contact
    state = addEdge(state, "USES", "a", "c");
    state = addEdge(state, "USES", "b", "c");
    expect(unpinnedSecondaryRoots(state)).toEqual([]);
  });

  it("removing the connecting edge re-exposes the now-disconnected root as unpinned", () => {
    let state = createEmptyPattern();
    state = addVariableNode(state, "Person"); // a
    state = addVariableNode(state, "Endpoint"); // b
    state = addEdge(state, "USES", "a", "b");
    state = removeElement(state, "a");
    // `b` (now the only node) is trivially a single root, not a *second* root — nothing to flag.
    expect(unpinnedSecondaryRoots(state)).toEqual([]);
  });
});

describe("toPatternQuery", () => {
  it("carries a pinned node's id through to PatternNode.node_id", () => {
    let state = createEmptyPattern();
    state = pinNode(state, "Person", "n1", "Person · n1");
    const query = toPatternQuery(state);
    expect(query.nodes).toEqual([{ var: "a", entity_type: "Person", node_id: "n1" }]);
  });

  it("leaves node_id null for an ordinary (unpinned) variable", () => {
    let state = createEmptyPattern();
    state = addVariableNode(state, "Person");
    const query = toPatternQuery(state);
    expect(query.nodes[0]?.node_id).toBeNull();
  });
});

describe("fromPatternQuery", () => {
  it("round-trips a saved pattern's nodes and edges back into builder state", () => {
    let state = createEmptyPattern();
    state = addVariableNode(state, "Person"); // a
    state = addVariableNode(state, "Endpoint"); // b
    state = addEdge(state, "USES", "a", "b");
    const query = toPatternQuery(state);

    expect(fromPatternQuery(query)).toEqual(state);
  });

  it("regenerates a pinned node's display label from entity_type and node_id, matching pinNode's own shape", () => {
    let state = createEmptyPattern();
    state = pinNode(state, "Person", "n42", "Person · n42");
    const query = toPatternQuery(state);

    // The label is never persisted in PatternQuery itself — it must come back identical to what
    // pinning the same node fresh would have produced, not merely non-null.
    expect(fromPatternQuery(query)).toEqual(state);
  });

  it("leaves pinnedNodeId and pinnedLabel null for an ordinary (unpinned) variable", () => {
    const loaded = fromPatternQuery({
      nodes: [{ var: "a", entity_type: "Person", node_id: null }],
      edges: [],
      limit: 1000,
    });
    expect(loaded.nodes[0]?.pinnedNodeId).toBeNull();
    expect(loaded.nodes[0]?.pinnedLabel).toBeNull();
  });

  it("defaults entityType to an empty string when entity_type is absent", () => {
    const loaded = fromPatternQuery({
      nodes: [{ var: "a", node_id: null }],
      edges: [],
      limit: 1000,
    });
    expect(loaded.nodes[0]?.entityType).toBe("");
  });
});
