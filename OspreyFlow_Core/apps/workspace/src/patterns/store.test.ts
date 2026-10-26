import { describe, expect, it } from "vitest";

import type { OntologySchema } from "../../../../packages/schemas/generated";
import {
  addCondition,
  addEdge,
  addVariableNode,
  conditionableProperties,
  createEmptyPattern,
  fromPatternQuery,
  isPatternRunnable,
  MAX_CONDITIONS,
  pinNode,
  removeCondition,
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

  it("lets an open second root share a contact with the first (ADR-100 Amendment 7)", () => {
    let state = createEmptyPattern();
    state = addVariableNode(state, "Person"); // a
    state = addVariableNode(state, "Endpoint"); // b, the shared contact
    state = addVariableNode(state, "Person"); // c, reached backwards from b
    state = addEdge(state, "USES", "c", "b"); // drawn first: the order it is drawn in is no matter
    state = addEdge(state, "USES", "a", "b");
    expect(unpinnedSecondaryRoots(state)).toEqual([]);
    expect(isPatternRunnable(state)).toBe(true);
  });

  it("lets a link join two variables already reached: two who share two contacts", () => {
    let state = createEmptyPattern();
    for (const type of ["Person", "Endpoint", "Person", "Endpoint"]) state = addVariableNode(state, type);
    state = addEdge(state, "USES", "a", "b");
    state = addEdge(state, "USES", "c", "b");
    state = addEdge(state, "USES", "a", "d");
    state = addEdge(state, "USES", "c", "d");
    expect(unpinnedSecondaryRoots(state)).toEqual([]);
  });

  it("still flags a root that no link reaches", () => {
    let state = createEmptyPattern();
    for (const type of ["Person", "Endpoint", "Person", "Endpoint"]) state = addVariableNode(state, type);
    state = addEdge(state, "USES", "a", "b");
    state = addEdge(state, "USES", "c", "d"); // c and d are a second, separate pattern
    expect(unpinnedSecondaryRoots(state).map((n) => n.var)).toEqual(["c"]);
    expect(isPatternRunnable(state)).toBe(false);
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

// ADR-121: a condition on a pattern node's property — equality, one value, at most three, on an
// indexed property the ontology does not mark sensitivity: high.
const CONDITION_SCHEMA = {
  version: 1,
  entity_types: [
    {
      name: "Establishment",
      pole_class: "place",
      channel: "teal",
      shape: "square",
      identifiers: [],
      properties: [
        { name: "niu_area", type: "string", indexed: true },
        { name: "regime", type: "enum", indexed: true, values: ["open", "closed"] },
        { name: "secret_code", type: "string", indexed: true, sensitivity: "high" },
        { name: "note", type: "string" },
        { name: "capacity", type: "integer", indexed: true },
        { name: "tags", type: "string[]", indexed: true },
      ],
    },
  ],
  edge_types: [],
} as unknown as OntologySchema;

describe("conditionableProperties", () => {
  it("offers only indexed text properties that are not sensitivity: high", () => {
    expect(conditionableProperties(CONDITION_SCHEMA, "Establishment").map((p) => p.name)).toEqual([
      "niu_area",
      "regime",
    ]);
  });

  it("offers nothing for a type the ontology does not hold", () => {
    expect(conditionableProperties(CONDITION_SCHEMA, "Nowhere")).toEqual([]);
  });
});

describe("conditions on a pattern node", () => {
  function withEstablishment() {
    return addVariableNode(createEmptyPattern(), "Establishment");
  }

  it("a new node carries none", () => {
    expect(withEstablishment().nodes[0]?.where).toEqual({});
  });

  it("carries a condition through to PatternNode.where, and omits the field when there is none", () => {
    const state = addCondition(withEstablishment(), "a", "niu_area", "North");
    expect(toPatternQuery(state).nodes[0]?.where).toEqual({ niu_area: "North" });
    expect("where" in (toPatternQuery(withEstablishment()).nodes[0] ?? {})).toBe(false);
  });

  it("round-trips through a saved pattern", () => {
    let state = addCondition(withEstablishment(), "a", "niu_area", "North");
    state = addCondition(state, "a", "regime", "open");
    expect(fromPatternQuery(toPatternQuery(state))).toEqual(state);
  });

  it("setting the same property again replaces its value, never adds a second entry", () => {
    let state = addCondition(withEstablishment(), "a", "niu_area", "North");
    state = addCondition(state, "a", "niu_area", "South");
    expect(state.nodes[0]?.where).toEqual({ niu_area: "South" });
  });

  it("trims the value and ignores an empty one", () => {
    let state = addCondition(withEstablishment(), "a", "niu_area", "  North ");
    expect(state.nodes[0]?.where).toEqual({ niu_area: "North" });
    state = addCondition(state, "a", "regime", "   ");
    expect(state.nodes[0]?.where).toEqual({ niu_area: "North" });
  });

  it(`stops at ${MAX_CONDITIONS} entries: a fourth property is not added`, () => {
    let state = withEstablishment();
    for (const name of ["p1", "p2", "p3", "p4"]) state = addCondition(state, "a", name, "x");
    expect(Object.keys(state.nodes[0]?.where ?? {})).toEqual(["p1", "p2", "p3"]);
    // Changing a value already held is still allowed at the limit.
    state = addCondition(state, "a", "p2", "y");
    expect(state.nodes[0]?.where).toEqual({ p1: "x", p2: "y", p3: "x" });
  });

  it("removes one condition and leaves the others and every other node alone", () => {
    let state = addVariableNode(withEstablishment(), "Person");
    state = addCondition(state, "a", "niu_area", "North");
    state = addCondition(state, "a", "regime", "open");
    state = removeCondition(state, "a", "niu_area");
    expect(state.nodes[0]?.where).toEqual({ regime: "open" });
    expect(state.nodes[1]?.where).toEqual({});
  });
});
