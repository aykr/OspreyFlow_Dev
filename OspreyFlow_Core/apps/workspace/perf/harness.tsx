// Perf-gate harness — loads the 50k/250k fixture directly into a working
// set (no server, no network) and renders `GlassCanvas` alone, so
// `perf.spec.ts` measures the canvas's own render/interaction cost, not
// HTTP/WebSocket latency. Not part of the shipped app; a standalone Vite
// entry point (`perf/harness.html`) `perf.spec.ts` points a Playwright
// page at directly.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import { generateFixture } from "./fixture";
import type { OntologySchema } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __PERF__?: { readyAt: number | null };
    /** What `perf/community-links.spec.ts` asks the canvas (ADR-119). */
    __CANVAS__?: Pick<GlassCanvasHandle, "linkDrawn" | "nodeDrawnAs" | "zoomTo" | "cameraState" | "selectLink" | "highlightNodes">;
  }
}

const FIXTURE_SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", identifiers: [] },
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon", identifiers: [] },
    { name: "Device", pole_class: "object", channel: "plum", shape: "square", identifiers: [] },
    {
      name: "Organisation",
      pole_class: "organisation",
      channel: "azure",
      shape: "square",
      identifiers: [],
    },
    { name: "Location", pole_class: "location", channel: "ochre", shape: "pin", identifiers: [] },
  ],
  edge_types: [{ name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false }],
};

window.__PERF__ = { readyAt: null };

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(FIXTURE_SCHEMA);

const { nodes, edges } = generateFixture();
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges });

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <GlassCanvas
    ref={(handle) => {
      window.__CANVAS__ = handle ?? undefined;
    }}
    graph={workingSet.graph}
    store={workingSet.store}
    ontology={ontology}
    edgeTypes={FIXTURE_SCHEMA.edge_types}
    investigationId="perf-fixture"
    apiBaseUrl="http://unused.invalid"
    bearerToken="unused"
  />,
);

// Sigma's own `afterRender` fires once per frame; the first one after
// mount is "first interactive frame" for this harness's purposes — the
// same event `perf.spec.ts` would have no other reliable hook for, since
// this harness never touches the network the real app's `onOpen`/delta
// events would otherwise mark readiness from.
requestAnimationFrame(() => {
  const observer = new MutationObserver(() => {
    const canvas = container.querySelector("canvas.sigma-nodes");
    if (canvas) {
      window.__PERF__!.readyAt = performance.now();
      observer.disconnect();
    }
  });
  observer.observe(container, { childList: true, subtree: true });
  // In case the canvas already exists by the time this runs:
  if (container.querySelector("canvas.sigma-nodes")) {
    window.__PERF__!.readyAt = performance.now();
    observer.disconnect();
  }
});
