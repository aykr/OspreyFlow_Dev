// Assessment-panel keyboard harness — a new surface needing its own equivalent of
// `keyboard.spec.ts`: the Judgements tab is the fifth keyboard-driven surface (`keyboard/harness.tsx`'s own
// `CANVAS_ACTIONS`, `metrics-panel-harness.tsx`'s own `METRICS_PANEL_ACTIONS`,
// `query-builder-harness.tsx`'s own `QUERY_BUILDER_ACTIONS`, `watch-panels-harness.tsx`'s own
// `WATCH_PANEL_ACTIONS`), so it gets its own harness. Mounts `JudgementsPanel` directly rather
// than the full `App`/`GlassCanvas` tree — the panel's own `onHighlightNodes` prop is exactly the
// seam `App.tsx` would otherwise wire to a real canvas, so a harness-level stand-in
// (`window.__ASSESSMENT_HARNESS__`) proves the same real callback fires with the same real
// argument, the same `window.__WATCH_HARNESS__` shape `watch-panels-harness.tsx` already uses for
// `AlertInbox`'s own `onOpenInvestigation`.
//
// `POST/GET /v1/investigations/{id}/judgements`, `.../gaps`, `.../assumptions` and
// `GET /v1/yardstick` are intercepted by `assessment-panel.spec.ts` via `page.route` — the same
// "real network call, mocked at the transport, not the component" shape every other keyboard
// spec in this directory already uses.
import Graph from "graphology";
import { createRoot } from "react-dom/client";

import "../../../docs/design/tokens.css";
import "../src/design/primitives.css";
import { JudgementsPanel } from "../src/assessment/JudgementsPanel";

declare global {
  interface Window {
    __ASSESSMENT_HARNESS__?: { highlightedNodeIds: string[] };
  }
}

window.__ASSESSMENT_HARNESS__ = { highlightedNodeIds: [] };

function buildGraph(): Graph {
  const graph = new Graph();
  graph.addNode("n1", { data: { type: "Person", properties: { family_name: "Mercer" } } });
  graph.addNode("n2", { data: { type: "Endpoint", properties: { value_normalised: "+447700900000" } } });
  return graph;
}

function Harness() {
  return (
    <div style={{ width: 480 }}>
      <JudgementsPanel
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        investigationId="inv-1"
        workingSetGraph={buildGraph()}
        selectedNodeId={null}
        onHighlightNodes={(nodeIds) => {
          window.__ASSESSMENT_HARNESS__!.highlightedNodeIds = nodeIds;
        }}
      />
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
