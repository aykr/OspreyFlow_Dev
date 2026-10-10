// Deck capture — the real Timeline under the real canvas, as App.tsx arranges them, over
// Operation Ledger's own fortnight: the structuring drumbeat, then the two large transfers. The
// histogram answer comes from `fraud.capture.ts`'s route stub, the same transport-level mocking
// the keyboard suite uses.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { GlassCanvas } from "../src/canvas/GlassCanvas";
import { createCrossFilterStore } from "../src/crossfilter/store";
import { OntologyRegistry } from "../src/ontology/schema";
import { Timeline } from "../src/timeline/Timeline";
import { createWorkingSet } from "../src/workingset/store";
import { FRAUD_EDGES, FRAUD_NODES, FRAUD_SCHEMA } from "./fraudFixture";

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(FRAUD_SCHEMA);
workingSet.store
  .getState()
  .applyDelta({ seq: 1, op: "snapshot", nodes: FRAUD_NODES, edges: FRAUD_EDGES, filtered_count: 0 });

const crossFilterStore = createCrossFilterStore("http://deck-capture.invalid", "unused", "inv-1");
// The analyst's brush: the structuring fortnight selected, so the trend outside it dims.
crossFilterStore.store.getState().setWindow({
  validFrom: "2026-09-01T00:00:00Z",
  validTo: "2026-09-15T00:00:00Z",
});

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(
  <div style={{ width: "100vw", height: "100vh", display: "grid", gridTemplateRows: "1fr 280px" }}>
    <div style={{ minHeight: 0 }}>
      <GlassCanvas
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
    <div style={{ borderTop: "1px solid var(--border-subtle)" }}>
      <Timeline
        apiBaseUrl="http://deck-capture.invalid"
        bearerToken="unused"
        investigationScope="inv-1"
        crossFilterStore={crossFilterStore}
        getNodeIds={() => []}
      />
    </div>
  </div>,
);
