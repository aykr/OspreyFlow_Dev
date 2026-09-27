// Keyboard-only walkthrough harness — `docs/02_GLASS_FRONTEND.md` §6's
// accessibility floor ("Every canvas action reachable by keyboard"),
// This phase's exit criterion ("Keyboard navigation
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
    __KEYBOARD__?: {
      focused: string | null;
      selection: string[];
      viewMessagesNodeId: string | null;
    };
  }
}

const SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] },
    // Phase 6a Stage 4 (B6): the only fixture data the "View messages" radial-menu item needs —
    // it is offered on `Endpoint`-type nodes specifically (`GlassCanvas.tsx`'s own condition).
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon", identifiers: [] },
  ],
  edge_types: [
    { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false },
    { name: "USES", from: ["Person"], to: ["Endpoint"], directed: true },
  ],
};

function node(id: string, overrides: Partial<Node> = {}): Node {
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
    ...overrides,
  };
}

function edge(id: string, source: string, target: string, type = "ASSOCIATE_OF"): Edge {
  return {
    id,
    type,
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

window.__KEYBOARD__ = { focused: null, selection: [], viewMessagesNodeId: null };

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(SCHEMA);

// A chain n0—n1—n2—n3: `graph.nodes()[0]` (Tab's keyboard entry point) is
// deterministically "n0", and it has exactly one neighbour ("n1"), so the
// arrow-walk assertion has one unambiguous correct answer.
//
// `n2`/`n3` additionally share a `resolution.cluster_id` (Phase 6a Stage 3) — the only fixture
// data needed for the radial menu's "Explain cluster" item to appear at all; it does not depend
// on a `SAME_AS`/`NOT_SAME_AS` edge existing, since `keyboard.spec.ts` mocks the `explain` network
// call rather than exercising a real backend, the same way the existing Enter/Space tests mock
// `expand`/`resolution/link`.
// `n4` is an `Endpoint`, reachable by walking one hop past `n3` (`USES`) — the only fixture data
// the "View messages" item needs to actually be reachable by keyboard, not merely present.
const nodes = [
  node("n0"),
  node("n1"),
  node("n2", { resolution: { cluster_id: "n2" } }),
  node("n3", { resolution: { cluster_id: "n2" } }),
  node("n4", { type: "Endpoint", properties: { value_normalised: "n4" } }),
  // **`n5` is deliberately disconnected — it has no edge to anything, ever.** Round 12d: every
  // other node here is on one chain, so arrow-walk (which follows `graph.neighbors`) can reach
  // all of them, and a walkthrough over this fixture could not tell whether the canvas had a
  // keyboard route to a *non-adjacent* node or merely to an adjacent one. It did not — which is
  // why `Explain cluster` and `Find paths to`, both gated on a two-node selection, were
  // mouse-only in practice for the case that actually matters: two entities found by identifier,
  // which is how an analyst reaches them and which leaves them unconnected until something is
  // expanded. `n5` is the fixture datum that makes that reachable-or-not question answerable.
  node("n5"),
];
const edges = [
  edge("e0", "n0", "n1"),
  edge("e1", "n1", "n2"),
  edge("e2", "n2", "n3"),
  edge("e3", "n3", "n4", "USES"),
];
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges, filtered_count: 0 });

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <>
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
      onViewMessages={(nodeId) => {
        window.__KEYBOARD__!.viewMessagesNodeId = nodeId;
      }}
    />
    {/* The Tab-trap fix's own proof needs a real next tab-stop after the canvas — nothing here
        before Phase 7 Stage 4, since the canvas's own onKeyDown used to intercept every Tab
        press regardless. */}
    <button id="after-canvas">After canvas</button>
  </>,
);
