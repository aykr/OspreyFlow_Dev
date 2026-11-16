// v0.6.1 glass-rows A and C (ADR-145 Amendment 19 decisions 5 and 6): the case line and the real canvas, wired as
// `App.tsx` wires them, by the same `useViewToolbar` (the toolbar hidden or shown, the setting the analyst's, focus
// moving between *Hide toolbar* and *Show toolbar*, T on the canvas) and the same `ResolutionThresholdControl` in the
// canvas toolbar after Layout. `glass-toolbar.spec.ts` and `keyboard.spec.ts` drive it; every-harness scans it.
//   ?user=…        the signed-in analyst (osprey-demo-analyst; `none` for nobody signed in);
//   ?width=…       the canvas's width in pixels, so the toolbar's own width decides its words;
//   ?view=map      the Map's row instead of the canvas (the row as App draws it; the map itself is not drawn);
//   ?open=strictness  the strictness control open; ?hidden=1 the toolbar hidden, as the analyst left it;
//   ?brand=govuk, ?theme=light the looks.
import { createRef, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import "../src/design/fonts";
import { applyHarnessBrand } from "./brandHarness";
import { loadLookFaces } from "./lookFaces";
import { Button } from "../src/design/primitives/Button";
import { GlassCanvas, type GlassCanvasHandle } from "../src/canvas/GlassCanvas";
import { HideToolbarButton, ShowToolbarButton } from "../src/canvas/ToolbarToggle";
import { useViewToolbar, VIEW_TOOLBAR_ID, writeToolbarHidden } from "../src/canvas/toolbarVisibility";
import { useCompactWidth } from "../src/canvas/toolbarCompact";
import { OntologyRegistry } from "../src/ontology/schema";
import { ResolutionThresholdControl } from "../src/resolution/ThresholdControl";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { ContextBanner } from "../src/shell/ContextBanner";
import { applyTheme } from "../src/theme/theme";
import { createWorkingSet } from "../src/workingset/store";
import type { Edge, Node, OntologySchema } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    __GLASS_TOOLBAR__?: {
      cameraState: () => { x: number; y: number; ratio: number } | null;
      canvasBox: () => { top: number; height: number } | null;
      said: string[];
    };
  }
}

const params = new URLSearchParams(window.location.search);
const brand = await applyHarnessBrand();
if (brand !== "govuk" && params.get("theme") === "light") applyTheme("light");
// The look's own faces loaded before anything is drawn or measured, and never left to blank the page (`lookFaces.ts`).
await loadLookFaces(["400", "600", "700"], ['400 12px "IBM Plex Mono"']);

const userParam = params.get("user");
const username = userParam === "none" ? null : (userParam ?? "osprey-demo-analyst");
const width = Number(params.get("width") ?? "");
const onMap = params.get("view") === "map";
if (params.get("hidden") === "1") writeToolbarHidden(username, true);

// The threshold the control reads and sets, answered here: Balanced, and an outcome for any stop chosen.
window.fetch = (async (url: string, init?: RequestInit) => {
  if (String(url).endsWith("/resolution/threshold")) {
    const body =
      init?.method === "PUT"
        ? { delta: { seq: 1, op: "reproject", reason: "threshold", affected_cluster_ids: {} }, merged: 2, split: 1, affected: 3 }
        : { threshold: 0.95 };
    return new Response(JSON.stringify(body), { status: 200 });
  }
  return new Response("{}", { status: 404 });
}) as typeof fetch;

const SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [{ name: "Person", pole_class: "person", channel: "indigo", shape: "circle", icon: "person", identifiers: [], properties: [{ name: "family_name", type: "string", indexed: true }] }],
  edge_types: [{ name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false }],
};
const handling = { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" } as const;
const provenance = { state: "asserted", sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }], first_seen: "2026-01-01T00:00:00Z" } as const;
const audit = { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" };
const nodes: Node[] = Array.from({ length: 6 }, (_, i) => ({ id: `n${i}`, type: "Person", properties: { family_name: `Person ${i}` }, provenance, handling, audit }) as Node);
const edges: Edge[] = nodes.slice(1).map((n, i) => ({ id: `e${i}`, type: "ASSOCIATE_OF", source: "n0", target: n.id, provenance, handling, audit }) as Edge);
const workingSet = createWorkingSet();
workingSet.store.getState().applyDelta({ seq: 1, op: "snapshot", nodes, edges });
const ontology = new OntologyRegistry(SCHEMA);
const canvasHandle = createRef<GlassCanvasHandle>();
const said: string[] = [];
window.__GLASS_TOOLBAR__ = {
  cameraState: () => canvasHandle.current?.cameraState() ?? null,
  canvasBox: () => {
    const box = document.querySelector('[role="application"][aria-label="Network canvas"]')?.getBoundingClientRect();
    return box ? { top: box.top, height: box.height } : null;
  },
  said,
};

function Screen() {
  const { hidden, toggle, toggleByKey, hideRef, showRef } = useViewToolbar(username, true);
  // As App: the canvas says whether its toolbar is narrow; the Map's row is measured on the column it spans.
  const [canvasCompact, setCanvasCompact] = useState(false);
  const column = useRef<HTMLDivElement | null>(null);
  const columnCompact = useCompactWidth(column);
  return (
    <div ref={column} style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <ClassificationStrip marking="OFFICIAL" />
      <ContextBanner
        place="glass"
        caseSwitcher={<button type="button" className="btn menu-button menu-button--case">Case: Kestrel ▾</button>}
        datasets={["Prison intel"]}
        onViews={() => undefined}
        savedViews={7}
        crossLink={{ label: "Open this case's data in the Ingest Studio ↗", shortLabel: "Open in the Ingest Studio ↗", onFollow: () => undefined }}
        slim={hidden}
        end={hidden ? <ShowToolbarButton ref={showRef} onToggle={toggle} compact={onMap ? columnCompact : canvasCompact} /> : undefined}
      />
      {onMap && (
        <div role="toolbar" aria-label="Map view" className="view-toolbar" id={VIEW_TOOLBAR_ID} hidden={hidden}>
          <Button>Add site</Button>
          <Button>Draw boundary</Button>
          <HideToolbarButton ref={hideRef} look="row" onToggle={toggle} />
        </div>
      )}
      <div style={{ flex: 1, display: "flex", minHeight: 0, position: "relative" }}>
        <main style={{ width: width > 0 ? width : undefined, flex: width > 0 ? "none" : 1, position: "relative", minWidth: 0 }}>
          {!onMap && (
            <GlassCanvas
              ref={canvasHandle}
              graph={workingSet.graph}
              store={workingSet.store}
              ontology={ontology}
              edgeTypes={SCHEMA.edge_types}
              entityTypes={SCHEMA.entity_types}
              investigationId="inv-1"
              apiBaseUrl="http://glass-toolbar.invalid"
              bearerToken="unused"
              lastChange="Last change: 2 entities added, 09:40"
              toolbarAfterLayout={
                <ResolutionThresholdControl
                  apiBaseUrl="http://glass-toolbar.invalid"
                  bearerToken="unused"
                  investigationId="inv-1"
                  store={workingSet.store}
                  onChangeSummary={(message) => said.push(message)}
                />
              }
              toolbarId={VIEW_TOOLBAR_ID}
              toolbarHidden={hidden}
              onToolbarKey={toggleByKey}
              onToolbarCompactChange={setCanvasCompact}
              toolbarEnd={<HideToolbarButton ref={hideRef} onToggle={toggle} />}
            />
          )}
        </main>
      </div>
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
createRoot(container).render(<Screen />);
if (params.get("open") === "strictness") {
  const button = await new Promise<HTMLButtonElement>((resolve) => {
    const look = () => {
      const found = document.querySelector<HTMLButtonElement>('button[aria-label^="Match strictness"]');
      if (found) resolve(found);
      else requestAnimationFrame(look);
    };
    look();
  });
  button.click();
}
