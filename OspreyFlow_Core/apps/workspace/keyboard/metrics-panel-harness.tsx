// Metrics-panel keyboard harness — a new surface needing its own equivalent of `keyboard.spec.ts`:
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

import "../src/design/tokens.css";
import { applyHarnessBrand } from "./brandHarness";
import "../src/design/primitives.css";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { MetricsPanel } from "../src/metrics/MetricsPanel";
import type { MetricFilter } from "../src/metrics/filters";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import type { OntologySchema, Node, Edge } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __METRICS_PANEL__?: {
      focusedNodeId: string | null;
      filter: MetricFilter | null;
      positionOf?: (nodeId: string) => { x: number; y: number } | null;
    };
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

window.__METRICS_PANEL__ = { focusedNodeId: null, filter: null };

const workingSet = createWorkingSet();
const ontology = new OntologyRegistry(SCHEMA);

const nodes = [node("n0"), node("n1"), node("n2")];
const edges = [edge("e0", "n0", "n1"), edge("e1", "n1", "n2")];
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges });

// ADR-139 decision 7: the case's connection-strength legend, drawn in the canvas's legend box.
const STRENGTH_LEGEND = {
  influencers: [
    {
      layer: "file" as const,
      version: null,
      influencer: {
        id: "direct", label: "Direct link", link_types: ["ASSOCIATE_OF"], change: "add" as const, size: 0.1348,
        trigger: null, note: "to be confirmed with the client",
      },
    },
    {
      layer: "case" as const,
      version: 1,
      influencer: {
        id: "case-assault", label: "Assault in this case", link_types: ["ASSOCIATE_OF"], change: "floor" as const,
        size: 0.6, trigger: { entity_type: "Incident", property: "category", values: ["assault"] },
      },
    },
  ],
  direct_link_types: ["ASSOCIATE_OF"],
  switched_off: [],
  rarity_note: "Shared-attribute rarity is worked out over what you may see: two analysts with different access can see different rarity for the same pair.",
  // ADR-139 Amendment 2: `?composition=client_parity` draws the case switched to client parity.
  ...(new URLSearchParams(window.location.search).get("composition") === "client_parity"
    ? { composition: "client_parity" as const, composition_layer: "case" as const, rarity_measure: "share" as const }
    : { composition: "standard" as const, composition_layer: "file" as const, rarity_measure: "share" as const }),
}; // prettier-ignore

function Harness() {
  const glassCanvasRef = useRef<GlassCanvasHandle>(null);
  // Where a node is drawn, so a case can ask whether centring put it in the middle.
  window.__METRICS_PANEL__!.positionOf = (nodeId) =>
    glassCanvasRef.current?.viewportPositionOf(nodeId) ?? null;
  // The shape `layoutSettled.ts` reads, so a case can wait for the first layout to finish.
  (window as unknown as { __CANVAS__: unknown }).__CANVAS__ = {
    viewportPositionOf: (nodeId: string) => glassCanvasRef.current?.viewportPositionOf(nodeId) ?? null,
  };
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
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          strengthLegend={STRENGTH_LEGEND as any}
          onFocusChange={(nodeId) => {
            window.__METRICS_PANEL__!.focusedNodeId = nodeId;
          }}
        />
      </div>
      {/* The panel scrolls inside its column, as it does in the product's side panel slot
          (`SidePanelStack`, overflow: auto). Without it the Filters section ran 10.6px past the column
          and the page's body, and axe read the last note as partly obscured (rules-hyg item 2). */}
      <div style={{ width: 300, height: 600, overflow: "auto" }}>
        <MetricsPanel
          apiBaseUrl="http://keyboard-test.invalid"
          bearerToken="unused"
          investigationId="metrics-panel-fixture"
          graph={workingSet.graph}
          onFocusNode={(nodeId) => glassCanvasRef.current?.focusOnNode(nodeId)}
          onFilterChange={(filter) => {
            window.__METRICS_PANEL__!.filter = filter;
          }}
        />
      </div>
    </div>
  );
}

await applyHarnessBrand();

// `?filter=strength` or `?filter=rarity` (ADR-139 decision 6): that metric chosen in the Filter
// section, its values answered by the page itself, for the axe scan. Synthetic (rule 9).
const FILTER = new URLSearchParams(window.location.search).get("filter");
if (FILTER) {
  window.fetch = async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.endsWith("/connection-strength")
      ? {
          links: [
            { edge_id: "e0", edge_type: "ASSOCIATE_OF", base_weight: 0.3, strength: 0.3, applied: [] },
            { edge_id: "e1", edge_type: "ASSOCIATE_OF", base_weight: 0.75, strength: 0.9, applied: [] },
          ],
          legend: { influencers: [], direct_link_types: [], switched_off: [], rarity_note: "" },
        }
      : url.endsWith("/rarity")
        ? { scope: "dataset", node_values: { n0: 0.4, n1: 2.2 }, pairs: [] }
        : { mode: "sync", values: { n0: 1, n1: 2, n2: 1 } };
    return new Response(JSON.stringify(body), { status: 200 });
  };
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);

if (FILTER) {
  const settle = () => new Promise((resolve) => setTimeout(resolve, 50));
  const header = () =>
    [...document.querySelectorAll<HTMLButtonElement>("button.accordion-section__header")].find(
      (b) => b.textContent?.trim() === "Filter",
    );
  for (let i = 0; i < 40 && !header(); i++) await settle();
  if (header()?.getAttribute("aria-expanded") === "false") header()?.click();
  const field = () => document.querySelector<HTMLSelectElement>('[aria-label="Filter by metric"]');
  for (let i = 0; i < 40 && !field(); i++) await settle();
  const select = field();
  if (select) {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")?.set?.call(
      select,
      FILTER === "rarity" ? "shared_attribute_rarity" : "connection_strength",
    );
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }
}
