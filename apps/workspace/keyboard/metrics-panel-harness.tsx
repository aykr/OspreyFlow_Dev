// Metrics-panel keyboard harness — `CLAUDE.md` rule 13's "or its equivalent for a new surface":
// the metrics panel is a second, separate keyboard-driven surface from `GlassCanvas`'s own canvas
// actions (`keyboard/harness.tsx`), so it gets its own harness rather than being folded into that
// one. Renders `GlassCanvas` and `MetricsPanel` together, wired exactly as `App.tsx` wires them —
// `MetricsPanel`'s row activation calls `GlassCanvas`'s own `focusOnNode` via the same
// `GlassCanvasHandle` ref `App.tsx` uses, not a harness-only shortcut.
//
// `POST .../compute/degree` is intercepted by `metrics-panel.spec.ts` via `page.route`, the same
// "real network call, mocked at the transport, not the component" shape `keyboard.spec.ts`'s own
// Enter-expand test already uses — this harness makes the real `fetch` call unmodified.
import { createRoot } from "react-dom/client";
import { useRef } from "react";

import "../../../docs/design/tokens.css";
import "../src/design/primitives.css";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { MetricsPanel } from "../src/metrics/MetricsPanel";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import type { OntologySchema, Node, Edge } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __METRICS_PANEL__?: { focusedNodeId: string | null };
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

window.__METRICS_PANEL__ = { focusedNodeId: null };

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(SCHEMA);

const nodes = [node("n0"), node("n1"), node("n2")];
const edges = [edge("e0", "n0", "n1"), edge("e1", "n1", "n2")];
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges, filtered_count: 0 });

function Harness() {
  const glassCanvasRef = useRef<GlassCanvasHandle>(null);
  return (
    <div style={{ display: "flex", width: 1100, height: 600 }}>
      <div style={{ width: 800, height: 600 }}>
        <GlassCanvas
          ref={glassCanvasRef}
          graph={workingSet.graph}
          store={workingSet.store}
          ontology={ontology}
          edgeTypes={SCHEMA.edge_types}
          investigationId="metrics-panel-fixture"
          apiBaseUrl="http://keyboard-test.invalid"
          bearerToken="unused"
          onFocusChange={(nodeId) => {
            window.__METRICS_PANEL__!.focusedNodeId = nodeId;
          }}
        />
      </div>
      <div style={{ width: 300, height: 600 }}>
        <MetricsPanel
          apiBaseUrl="http://keyboard-test.invalid"
          bearerToken="unused"
          investigationId="metrics-panel-fixture"
          graph={workingSet.graph}
          onFocusNode={(nodeId) => glassCanvasRef.current?.focusOnNode(nodeId)}
        />
      </div>
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
