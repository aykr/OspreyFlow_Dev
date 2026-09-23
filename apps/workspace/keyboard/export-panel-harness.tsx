// Export-panel keyboard harness — a new surface needing its own equivalent of `keyboard.spec.ts`:
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
//
// Phase 8 Stage 4h: `onExportChartImage` is supplied as a fake here, not the real
// `GlassCanvasHandle.exportImage` — this harness mounts `ExportPanel` alone, with no live
// `GlassCanvas`/Sigma instance to capture from (this file's own header already establishes "mount
// the panel, not the shell"). The download-triggering keyboard case exercises the *subgraph*
// shape instead, which is fully real here (`buildSubgraphArtefact` needs only the graph already
// built below), so the fake below exists only so the chart option in the `Select` is not left
// broken if a future case exercises it.
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
        onExportChartImage={() => Promise.resolve(new Blob(["fake-png"], { type: "image/png" }))}
      />
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
