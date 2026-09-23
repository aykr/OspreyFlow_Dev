// Chart-capture harness — proves `captureChartImage` (`src/export/chartExport.ts`) against a
// real, WebGL-rendered `Sigma` instance, the one thing this project's own vitest environment
// cannot do (`chartExport.ts`'s own module docstring: no WebGL context in `node`/`jsdom`, no
// existing vitest render mounts a real `GlassCanvas` at all). This is that missing proof — a
// standalone Vite entry point a real Playwright browser loads directly, the same shape
// `perf/harness.tsx` already established for "needs a real renderer, not a fake one."
//
// A real, populated `GlassCanvas` — several nodes across two distinct entity-type channels, one
// edge — so the captured PNG has real visual content to assert on (non-uniform pixels, several
// distinct colours), not an empty canvas that would pass the same assertions a blank one would.
import { createRoot } from "react-dom/client";

import "../../../docs/design/tokens.css";
import "../src/design/primitives.css";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import type { ExportMark } from "../src/export/api";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import type { Edge, Node, OntologySchema } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __captureChartExport__?: (mark: ExportMark) => Promise<{
      bytes: number[];
      width: number;
      height: number;
    }>;
  }
}

const FIXTURE_SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] },
    {
      name: "Organisation",
      pole_class: "organisation",
      channel: "azure",
      shape: "square",
      identifiers: [],
    },
  ],
  edge_types: [{ name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false }],
};

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(FIXTURE_SCHEMA);

const HANDLING = {
  classification: "OFFICIAL",
  handling_code: "P",
  owning_unit: "unit-1",
  originator: "unit-1",
};

const PROVENANCE = {
  state: "asserted" as const,
  sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
  first_seen: "2026-01-01T00:00:00Z",
};

const AUDIT = { created_at: "2026-01-01T00:00:00Z", created_by: "export-capture-fixture" };

function person(id: string, familyName: string): Node {
  return {
    id,
    type: "Person",
    properties: { family_name: familyName },
    handling: HANDLING,
    provenance: PROVENANCE,
    audit: AUDIT,
  };
}

function org(id: string, name: string): Node {
  return {
    id,
    type: "Organisation",
    properties: { name },
    handling: HANDLING,
    provenance: PROVENANCE,
    audit: AUDIT,
  };
}

function assocEdge(id: string, source: string, target: string): Edge {
  return {
    id,
    type: "ASSOCIATE_OF",
    source,
    target,
    weight: 1,
    occurrences: 1,
    handling: HANDLING,
    provenance: PROVENANCE,
    audit: AUDIT,
  };
}

const nodes: Node[] = [
  person("n1", "Mercer"),
  person("n2", "Okafor"),
  person("n3", "Ahmed"),
  org("n4", "Ring Holdings"),
];
const edges: Edge[] = [assocEdge("e1", "n1", "n2"), assocEdge("e2", "n2", "n3")];

workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges, filtered_count: 0 });

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

let handle: GlassCanvasHandle | null = null;

createRoot(container).render(
  <GlassCanvas
    ref={(h) => {
      handle = h;
    }}
    graph={workingSet.graph}
    store={workingSet.store}
    ontology={ontology}
    edgeTypes={FIXTURE_SCHEMA.edge_types}
    investigationId="export-capture-fixture"
    apiBaseUrl="http://unused.invalid"
    bearerToken="unused"
  />,
);

window.__captureChartExport__ = async (mark: ExportMark) => {
  if (!handle) throw new Error("GlassCanvas handle not mounted");
  const blob = await handle.exportImage(mark);
  const buf = await blob.arrayBuffer();
  const bytes = Array.from(new Uint8Array(buf));
  const bitmap = await createImageBitmap(blob);
  return { bytes, width: bitmap.width, height: bitmap.height };
};
