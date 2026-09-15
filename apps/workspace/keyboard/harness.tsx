// Keyboard-only walkthrough harness — `docs/02_GLASS_FRONTEND.md` §6's
// accessibility floor ("Every canvas action reachable by keyboard"),
// `docs/07_BUILD_PLAN.md` Phase 4's exit criterion ("Keyboard navigation
// reaches every canvas action"). A small, real graph (not the 50k perf
// fixture — this test is about reachability, not scale) rendered with
// `GlassCanvas` alone, exposing `window.__KEYBOARD__` so
// `keyboard.spec.ts` can observe focus/selection state it has no other
// way to reach, and a real `expand` network call `keyboard.spec.ts`
// intercepts via `page.route` rather than this harness faking it.
import { createRoot } from "react-dom/client";

import "../../../docs/design/tokens.css";
import "../src/design/primitives.css";
import { GlassCanvas } from "../src/canvas/GlassCanvas";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import type { OntologySchema, Node, Edge } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __KEYBOARD__?: { focused: string | null; selection: string[] };
  }
}

const SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] },
  ],
  edge_types: [{ name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false }],
};

function node(id: string): Node {
  return {
    id,
    type: "Person",
    properties: { family_name: id },
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: {
      classification: "OFFICIAL",
      handling_code: "P",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  };
}

function edge(id: string, source: string, target: string): Edge {
  return {
    id,
    type: "ASSOCIATE_OF",
    source,
    target,
    provenance: {
      state: "asserted",
      sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }],
      first_seen: "2026-01-01T00:00:00Z",
    },
    handling: {
      classification: "OFFICIAL",
      handling_code: "P",
      originator: "unit-1",
      owning_unit: "unit-1",
    },
    audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
  };
}

window.__KEYBOARD__ = { focused: null, selection: [] };

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(SCHEMA);

// A chain n0—n1—n2—n3: `graph.nodes()[0]` (Tab's keyboard entry point) is
// deterministically "n0", and it has exactly one neighbour ("n1"), so the
// arrow-walk assertion has one unambiguous correct answer.
const nodes = ["n0", "n1", "n2", "n3"].map(node);
const edges = [edge("e0", "n0", "n1"), edge("e1", "n1", "n2"), edge("e2", "n2", "n3")];
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges, filtered_count: 0 });

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <GlassCanvas
    graph={workingSet.graph}
    store={workingSet.store}
    ontology={ontology}
    edgeTypes={SCHEMA.edge_types}
    investigationId="keyboard-fixture"
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    onFocusChange={(nodeId) => {
      window.__KEYBOARD__!.focused = nodeId;
    }}
    onSelectionChange={(ids) => {
      window.__KEYBOARD__!.selection = ids;
    }}
  />,
);
