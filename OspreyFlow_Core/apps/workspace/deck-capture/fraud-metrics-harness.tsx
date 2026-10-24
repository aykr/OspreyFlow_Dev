// Deck capture — the canvas beside the Metrics panel (the social-network analysis surface), over
// the Operation Ledger fixture. The compute answers come from `fraud.capture.ts`'s route stubs,
// the same transport-level mocking the keyboard suite uses.
import { useRef } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { MetricsPanel } from "../src/metrics/MetricsPanel";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import { FRAUD_EDGES, FRAUD_NODES, FRAUD_SCHEMA } from "./fraudFixture";

declare global {
  interface Window {
    __CANVAS__?: { viewportPositionOf: (nodeId: string) => { x: number; y: number } | null };
  }
}

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(FRAUD_SCHEMA);
workingSet.store
  .getState()
  .applyDelta({ seq: 1, op: "snapshot", nodes: FRAUD_NODES, edges: FRAUD_EDGES });

function Harness() {
  const canvas = useRef<GlassCanvasHandle>(null);
  window.__CANVAS__ = {
    viewportPositionOf: (nodeId) => canvas.current?.viewportPositionOf(nodeId) ?? null,
  };
  return (
    <div style={{ display: "flex", width: "100vw", height: "100vh" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <GlassCanvas
          ref={canvas}
          graph={workingSet.graph}
          store={workingSet.store}
          ontology={ontology}
          edgeTypes={FRAUD_SCHEMA.edge_types}
          entityTypes={FRAUD_SCHEMA.entity_types}
          investigationId="deck-fraud-fixture"
          apiBaseUrl="http://deck-capture.invalid"
          bearerToken="unused"
        />
      </div>
      <div style={{ width: 340, borderLeft: "1px solid var(--border-subtle)", overflow: "auto" }}>
        <MetricsPanel
          apiBaseUrl="http://deck-capture.invalid"
          bearerToken="unused"
          investigationId="deck-fraud-fixture"
          graph={workingSet.graph}
          onFocusNode={(nodeId) => canvas.current?.focusOnNode(nodeId)}
          onFilterChange={() => undefined}
        />
      </div>
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Harness />);
