import Graph from "graphology";
import { describe, expect, it } from "vitest";

import { buildSubgraphArtefact, serialiseSubgraphArtefact } from "./subgraphExport";
import type { ExportManifest, ExportMark } from "./api";

const MARK: ExportMark = {
  osprey_mark: "OspreyFlow",
  investigation_id: "inv-1",
  exported_at: "2026-09-23T00:00:00Z",
  resolution_threshold: 0.95,
  handling_level: "OFFICIAL",
};

const MANIFEST: ExportManifest = {
  policy: "disclose",
  withheld: true,
};

function fixtureGraph(): Graph {
  const graph = new Graph();
  graph.addNode("n1", { data: { id: "n1", type: "Person", family_name: "Mercer" } });
  graph.addNode("n2", { data: { id: "n2", type: "Organisation", name: "Fixture Corp" } });
  graph.addEdge("n1", "n2", { data: { id: "e1", type: "EMPLOYED_BY" } });
  return graph;
}

describe("subgraph export — test_subgraph_export_produces_real_json_carrying_the_mark", () => {
  it("produces well-formed JSON reusing the working set's own Node/Edge wire shape", () => {
    const artefact = buildSubgraphArtefact(fixtureGraph(), MARK, MANIFEST);

    expect(artefact.nodes).toEqual([
      { id: "n1", type: "Person", family_name: "Mercer" },
      { id: "n2", type: "Organisation", name: "Fixture Corp" },
    ]);
    expect(artefact.edges).toEqual([{ id: "e1", type: "EMPLOYED_BY" }]);
  });

  it("carries the mark and manifest as top-level structured fields", () => {
    const artefact = buildSubgraphArtefact(fixtureGraph(), MARK, MANIFEST);
    expect(artefact.mark).toEqual(MARK);
    expect(artefact.manifest).toEqual(MANIFEST);
  });

  it("serialises to real, parseable JSON — well-formed in its own format", () => {
    const artefact = buildSubgraphArtefact(fixtureGraph(), MARK, MANIFEST);
    const text = serialiseSubgraphArtefact(artefact);

    const parsed = JSON.parse(text);
    expect(parsed.mark.osprey_mark).toBe("OspreyFlow");
    expect(parsed.manifest.withheld).toBe(true);
    expect(parsed.manifest).not.toHaveProperty("withheld_count");
    expect(parsed.nodes).toHaveLength(2);
    expect(parsed.edges).toHaveLength(1);
  });

  it("an artefact built without a mark object is distinguishable from one that carries it — the negative control", () => {
    const artefact = buildSubgraphArtefact(fixtureGraph(), MARK, MANIFEST);
    const text = serialiseSubgraphArtefact(artefact);
    expect(text).toContain('"osprey_mark": "OspreyFlow"');

    const unmarked = JSON.stringify({ nodes: artefact.nodes, edges: artefact.edges });
    expect(unmarked).not.toContain("osprey_mark");
  });
});
