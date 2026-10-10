// Pure edits to a pipeline graph (ADR-108 phase B): each returns a new graph, never mutates, and
// never produces what the save gate would refuse by construction alone (ids unique, edges real).
import { describe, expect, it } from "vitest";

import type { PipelineGraph } from "../../../../../packages/schemas/generated";
import { addExtractAfter, addSourceChain, connectNodes, removeNode } from "./pipelineGraphEdit";

const CHAIN: PipelineGraph = {
  nodes: [
    { id: "domain", kind: "domain_model", label: "Domain model", config: { pack: "pole" } },
    { id: "source", kind: "source", label: "S", config: {} },
    { id: "profile", kind: "profile", label: "P", config: {} },
    { id: "map", kind: "map", label: "M", config: {} },
    { id: "load", kind: "load", label: "L", config: {} },
  ],
  edges: [
    { source: "domain", target: "source" },
    { source: "source", target: "profile" },
    { source: "profile", target: "map" },
    { source: "map", target: "load" },
  ],
};

describe("addSourceChain", () => {
  it("appends a whole source→profile→map→load branch wired to the domain", () => {
    const grown = addSourceChain(CHAIN, "Subscriber list");
    expect(grown.nodes).toHaveLength(9);
    expect(CHAIN.nodes).toHaveLength(5); // never mutated
    const added = grown.nodes!.filter((n) => !CHAIN.nodes!.some((o) => o.id === n.id));
    expect(added.map((n) => n.kind)).toEqual(["source", "profile", "map", "load"]);
    const ids = grown.nodes!.map((n) => n.id);
    expect(new Set(ids).size).toBe(ids.length);
    const newSource = added[0]!;
    expect(grown.edges).toContainEqual({ source: "domain", target: newSource.id });
    expect(newSource.label).toBe("Subscriber list");
  });
});

describe("addExtractAfter", () => {
  it("hangs an extract and its own load off a map node", () => {
    const grown = addExtractAfter(CHAIN, "map");
    const added = grown.nodes!.filter((n) => !CHAIN.nodes!.some((o) => o.id === n.id));
    expect(added.map((n) => n.kind)).toEqual(["extract", "load"]);
    expect(grown.edges).toContainEqual({ source: "map", target: added[0]!.id });
    expect(grown.edges).toContainEqual({ source: added[0]!.id, target: added[1]!.id });
  });
});

describe("removeNode", () => {
  it("removes the node and every edge that names it", () => {
    const grown = addExtractAfter(CHAIN, "map");
    const extract = grown.nodes!.find((n) => n.kind === "extract")!;
    const shrunk = removeNode(grown, extract.id);
    expect(shrunk.nodes!.some((n) => n.id === extract.id)).toBe(false);
    expect(shrunk.edges!.some((e) => e.source === extract.id || e.target === extract.id)).toBe(false);
  });
});

describe("connectNodes", () => {
  it("adds one edge and never a duplicate", () => {
    const once = connectNodes(CHAIN, "map", "load");
    expect(once.edges).toHaveLength(CHAIN.edges!.length);
    const grown = addSourceChain(CHAIN, "Second");
    const newMap = grown.nodes!.filter((n) => n.kind === "map").at(-1)!;
    const connected = connectNodes(grown, "source", newMap.id);
    expect(connected.edges).toContainEqual({ source: "source", target: newMap.id });
  });
});
