// Keyboard-only walkthrough harness — `spec/02_GLASS_FRONTEND.md` §6's
// accessibility floor ("Every canvas action reachable by keyboard"),
// This phase's exit criterion ("Keyboard navigation
// reaches every canvas action"). A small, real graph (not the 50k perf
// fixture — this test is about reachability, not scale) rendered with
// `GlassCanvas` alone, exposing `window.__KEYBOARD__` so
// `keyboard.spec.ts` can observe focus/selection state it has no other
// way to reach, and a real `expand` network call `keyboard.spec.ts`
// intercepts via `page.route` rather than this harness faking it.
import { createRoot } from "react-dom/client";
import { createRef } from "react";

import "../src/design/tokens.css";
import { applyTheme } from "../src/theme/theme";
import "../src/design/primitives.css";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import type { OntologySchema, Node, Edge } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __KEYBOARD__?: {
      focused: string | null;
      selection: string[];
      viewMessagesNodeId: string | null;
      selectedEdge: string | null;
    };
    __CANVAS__?: {
      viewportPositionOf: (nodeId: string) => { x: number; y: number } | null;
      expandFrom: (nodeId: string, depth: number) => void;
      /** The fill colour stored on a node now, which is what the canvas paints it with. */
      nodeColour: (nodeId: string) => string | null;
      setTheme: (theme: "dark" | "light") => void;
    };
    /** How many nodes are folded into Group Nodes now (ADR-066). */
    __GROUPED__?: number;
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

const canvasHandle = createRef<GlassCanvasHandle>();
window.__CANVAS__ = {
  viewportPositionOf: (id) => canvasHandle.current?.viewportPositionOf(id) ?? null,
  expandFrom: (id, depth) => canvasHandle.current?.expandFrom(id, depth),
  nodeColour: (id) => (workingSet.graph.hasNode(id) ? (workingSet.graph.getNodeAttribute(id, "color") as string) : null),
  setTheme: (theme) => applyTheme(theme),
};

window.__KEYBOARD__ = { focused: null, selection: [], viewMessagesNodeId: null, selectedEdge: null };

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
// `?fixture=communities` swaps the chain for two groups of five people, each a hub (`a0`, `b0`)
// with four others round it, joined by one link (a0—b0): what Communities (ADR-066) has to find,
// fold and open. A group is a wheel rather than every-person-to-every-person on purpose: a fully
// linked group of five is pulled into one point by the organic layout, which makes a test of where
// things are drawn meaningless.
const wantsCommunities = new URLSearchParams(window.location.search).get("fixture") === "communities";
if (wantsCommunities) {
  nodes.length = 0;
  edges.length = 0;
  for (const prefix of ["a", "b"]) {
    for (let i = 0; i < 5; i++) nodes.push(node(`${prefix}${i}`));
    for (let i = 1; i < 5; i++) edges.push(edge(`${prefix}0-${prefix}${i}`, `${prefix}0`, `${prefix}${i}`));
    for (let i = 1; i < 5; i++) {
      const next = i === 4 ? 1 : i + 1;
      edges.push(edge(`${prefix}${i}-${prefix}${next}`, `${prefix}${i}`, `${prefix}${next}`));
    }
  }
  edges.push(edge("bridge", "a0", "b0"));
}
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges, filtered_count: 0 });

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// `?judged=n1:2,n2:1` gives those nodes that many judgements, for the count drawn beside a node
// (ADR-070).
const judged = new Map<string, number>(
  (new URLSearchParams(window.location.search).get("judged") ?? "")
    .split(",")
    .filter(Boolean)
    .map((pair) => {
      const [id = "", count = "0"] = pair.split(":");
      return [id, Number(count)] as [string, number];
    }),
);

createRoot(container).render(
  <>
    <GlassCanvas
      ref={canvasHandle}
      judgementCounts={judged}
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
      onEdgeSelect={(edge) => {
        window.__KEYBOARD__!.selectedEdge = edge ? edge.id : null;
      }}
      onViewMessages={(nodeId) => {
        window.__KEYBOARD__!.viewMessagesNodeId = nodeId;
      }}
      onGroupedCountChange={(count) => {
        window.__GROUPED__ = count;
      }}
    />
    {/* The Tab-trap fix's own proof needs a real next tab-stop after the canvas — nothing here
        before Phase 7 Stage 4, since the canvas's own onKeyDown used to intercept every Tab
        press regardless. */}
    <button id="after-canvas">After canvas</button>
  </>,
);
