// Query-builder keyboard harness — a new surface needing its own equivalent of `keyboard.spec.ts`:
// the visual query builder is the third keyboard-driven surface (`keyboard/harness.tsx`'s own
// `CANVAS_ACTIONS`, `keyboard/metrics-panel-harness.tsx`'s own `METRICS_PANEL_ACTIONS`), so it
// gets its own harness rather than being folded into either. Renders `QueryBuilderPanel` alone —
// unlike the metrics panel, nothing here drives `GlassCanvas` yet (App.tsx's own wiring of both
// surfaces together is a later, separate change), so there is no second component to coordinate.
//
// `POST /v1/search`, `/v1/patterns/preview` and `/v1/patterns/run` are intercepted by
// `query-builder.spec.ts` via `page.route` — the same "real network call, mocked at the
// transport, not the component" shape `metrics-panel.spec.ts` already uses.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { QueryBuilderPanel } from "../src/patterns/QueryBuilderPanel";
import type { OntologySchema } from "../../../packages/schemas/generated";

const SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    {
      name: "Person",
      pole_class: "person",
      channel: "indigo",
      shape: "circle",
      identifiers: [],
      // ADR-121: one property a condition may name, and two it may not (sensitivity: high, and not
      // indexed), so the field offers exactly one.
      properties: [
        { name: "family_name", type: "string", indexed: true },
        { name: "date_of_birth", type: "date", sensitivity: "high" },
        { name: "list_name", type: "string" },
      ],
    },
    { name: "Endpoint", pole_class: "thing", channel: "teal", shape: "square", identifiers: [] },
  ],
  edge_types: [{ name: "USES", from: ["Person"], to: ["Endpoint"], directed: true }],
};

function Harness() {
  return (
    <div style={{ width: 480, height: 680 }}>
      <QueryBuilderPanel
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        investigationId="inv-1"
        schema={SCHEMA}
        selectedNodeIds={["n-selected"]}
      />
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
