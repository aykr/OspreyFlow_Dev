// Deck capture — the real network canvas over the Operation Ledger fixture (synthetic, rule 9).
// Not a test harness: `deck-capture/fraud.capture.ts` photographs it for the product deck.
import { createRef } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
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
  .applyDelta({ seq: 1, op: "snapshot", nodes: FRAUD_NODES, edges: FRAUD_EDGES, filtered_count: 0 });

const canvasHandle = createRef<GlassCanvasHandle>();
const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

window.__CANVAS__ = {
  viewportPositionOf: (nodeId) => canvasHandle.current?.viewportPositionOf(nodeId) ?? null,
};

createRoot(container).render(
  <div style={{ width: "100vw", height: "100vh", background: "var(--bg-canvas, var(--surface-base))" }}>
    <GlassCanvas
      ref={canvasHandle}
      graph={workingSet.graph}
      store={workingSet.store}
      ontology={ontology}
      edgeTypes={FRAUD_SCHEMA.edge_types}
      entityTypes={FRAUD_SCHEMA.entity_types}
      investigationId="deck-fraud-fixture"
      apiBaseUrl="http://deck-capture.invalid"
      bearerToken="unused"
    />
  </div>,
);
