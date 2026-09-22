// Export-panel keyboard harness — `CLAUDE.md` rule 13's "or its equivalent for a new surface":
// the export drawer is the sixth keyboard-driven surface (`keyboard/harness.tsx`'s own
// `CANVAS_ACTIONS`, `metrics-panel-harness.tsx`'s own `METRICS_PANEL_ACTIONS`,
// `query-builder-harness.tsx`'s own `QUERY_BUILDER_ACTIONS`, `watch-panels-harness.tsx`'s own
// `WATCH_PANEL_ACTIONS`, `assessment-panel-harness.tsx`'s own `ASSESSMENT_PANEL_ACTIONS`), so it
// gets its own harness. Mounts `ExportPanel` directly, always `open`, rather than the full
// `App`/`GlassCanvas` tree — the same "mount the panel, not the shell" shape
// `assessment-panel-harness.tsx` already established.
//
// `POST /v1/investigations/{id}/export` and `GET .../resolution/threshold` are intercepted by
// `export-panel.spec.ts` via `page.route` — the same "real network call, mocked at the transport,
// not the component" shape every other keyboard spec in this directory already uses.
import Graph from "graphology";
import { createRoot } from "react-dom/client";

import "../../../docs/design/tokens.css";
import "../src/design/primitives.css";
import { ExportPanel } from "../src/export/ExportPanel";

function buildGraph(): Graph {
  const graph = new Graph();
  graph.addNode("n1", {
    data: {
      type: "Person",
      properties: { family_name: "Mercer" },
      handling: {
        classification: "OFFICIAL",
        handling_code: "P",
        owning_unit: "unit-1",
        originator: "unit-1",
      },
    },
  });
  return graph;
}

function Harness() {
  return (
    <div style={{ width: 480 }}>
      <ExportPanel
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        investigationId="inv-1"
        graph={buildGraph()}
        open={true}
        onClose={() => undefined}
      />
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
