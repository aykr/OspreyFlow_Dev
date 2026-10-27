// The workspace shell's top (ADR-065, ADR-097 step 1): the classification strip, the real `TopBar`
// `App.tsx` renders (the mark, the case menu, the search box with its Filters icon, the view switch,
// Export and the account menu), and the left rail beside it. `fetch` answers the case list; the
// outcomes are exposed on `window.__TOPBAR__` for the specs.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { LeftRail } from "../src/shell/LeftRail";
import { TopBar } from "../src/shell/TopBar";
import { AccountMenu } from "../src/auth/AccountMenu";
import { Button } from "../src/design/primitives/Button";
import { CaseSwitcher } from "../src/investigation/CaseSwitcher";
import { GlobalSearch } from "../src/search/GlobalSearch";
import { GlassCanvas } from "../src/canvas/GlassCanvas";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import type { OntologySchema } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    /** With `?canvas=1`: whether the real canvas holds a node, and how many it holds. */
    __TOPBAR_CANVAS__?: { hasNode: (id: string) => boolean; count: () => number };
    __TOPBAR__?: { opened: string | null; browsed: boolean; signedOut: boolean; rail: string[]; views: string[]; help?: number };
  }
}

window.__TOPBAR__ = { opened: null, browsed: false, signedOut: false, rail: [], views: [] };

const CASES = [
  { id: "c1", name: "Enron corpus (real data, this machine only)", level: "author", created_at: "2026-09-29T09:00:00Z", created_by: "a" },
  { id: "c2", name: "PaySim mobile money (internal)", level: "viewer", created_at: "2026-09-28T09:00:00Z", created_by: "b" },
];
// Ten suggestions with more behind them, so the "Showing the first 10; more match" hint appears.
const SUGGESTIONS = Array.from({ length: 10 }, (_, i) => ({
  id: `e${i}`,
  type: "Endpoint",
  properties: { value_normalised: `person${i}@enron.com` },
}));
// ADR-128 decision 1 (B2): what "Add many from a list" sent, for `shell.spec.ts` to read back.
const LISTED_NODE = {
  id: "n-listed-1",
  type: "Person",
  properties: { family_name: "Listed" },
  provenance: { state: "asserted", sources: [{ document_id: "fixture-doc", locator: "p.1", excerpt_hash: "a".repeat(64) }], first_seen: "2026-01-01T00:00:00Z" },
  handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" },
  audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" },
};
const addMany: string[] = [];
(window as unknown as { __ADD_MANY__: string[] }).__ADD_MANY__ = addMany;
window.fetch = (async (url: string, init?: RequestInit) => {
  if (String(url).endsWith("/working-set/add-by-identifiers")) {
    const sent = String(init?.body ?? "");
    addMany.push(sent);
    const counts = { read: 2, found: 1, matched_nothing: 1, repeated: 0 };
    // Confirmed (`?canvas=1` proves it): the one node found, as the server's `add` delta.
    const confirmed = (JSON.parse(sent) as { confirm?: boolean }).confirm === true;
    const added = confirmed
      ? { delta: { seq: 1, op: "add", nodes: [LISTED_NODE], edges: [] }, links_among: "not_asked" }
      : null;
    return { ok: true, status: 200, json: async () => ({ counts, added }) };
  }
  const body = String(url).endsWith("/suggest") ? { nodes: SUGGESTIONS, more: true } : CASES;
  return { ok: true, status: 200, json: async () => body };
}) as unknown as typeof fetch;

// `?canvas=1` puts the real canvas where the stand-in is, and wires the search box's "Add many from a
// list" to its working set as `App.tsx`'s `applyStarterDelta` does (rule 13).
const wantsCanvas = new URLSearchParams(window.location.search).get("canvas") === "1";
const CANVAS_SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle", icon: "person", identifiers: [] },
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon", icon: "device", identifiers: [] },
  ],
  edge_types: [{ name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false }],
};
const workingSet = createWorkingSet();
const canvasOntology = new OntologyRegistry(CANVAS_SCHEMA);
window.__TOPBAR_CANVAS__ = {
  hasNode: (id) => workingSet.graph.hasNode(id),
  count: () => workingSet.graph.order,
};

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

const rail = (id: string) => () => window.__TOPBAR__!.rail.push(id);

createRoot(container).render(
  <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
    <ClassificationStrip marking="OFFICIAL" />
    <TopBar
      app="glass"
      caseSwitcher={
        <CaseSwitcher
          apiBaseUrl="http://top-bar.invalid"
          bearerToken="unused"
          currentId="c1"
          onOpen={(id) => {
            window.__TOPBAR__!.opened = id;
          }}
          onBrowse={() => {
            window.__TOPBAR__!.browsed = true;
          }}
        />
      }
      search={
        <GlobalSearch apiBaseUrl="http://top-bar.invalid" bearerToken="unused" investigationId="inv-1" entityTypes={["Person", "Endpoint"]} onSelect={() => undefined} onApplyDelta={(delta) => workingSet.store.getState().applyDelta(delta)} />
      }
      views={[
        { id: "graph", label: "Graph", pressed: true, onSelect: () => window.__TOPBAR__!.views.push("graph") },
        { id: "map", label: "Map", pressed: false, onSelect: () => window.__TOPBAR__!.views.push("map") },
        // ADR-111: as `App.tsx` offers it.
        { id: "reports", label: "Reports", pressed: false, onSelect: () => window.__TOPBAR__!.views.push("reports") },
      ]}
      actions={<Button>Export ⚙</Button>}
      account={
        <>
          {/* ADR-097 step 3: the theme is in the account menu, as in `App.tsx`. */}
          <AccountMenu
            principal={{
              sub: "2a0683a4-5a9c-40cb-94b9-e9c502084449",
              username: "osprey-demo-analyst",
              clearance: "OFFICIAL",
              orgUnit: "unit-1",
              roles: [],
              receivableHandlingCodes: [],
            }}
            onSignOut={() => {
              window.__TOPBAR__!.signedOut = true;
            }}
          />
        </>
      }
    />
    <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
      <LeftRail
        onHelp={() => { window.__TOPBAR__!.help = (window.__TOPBAR__!.help ?? 0) + 1; }}
        items={[
          { id: "cases", label: "Cases", icon: "cases", onSelect: rail("cases") },
          { id: "watches", label: "Watches", icon: "watches", onSelect: rail("watches") },
          { id: "alerts", label: "Alerts", icon: "alerts", onSelect: rail("alerts") },
          { id: "ownership", label: "Ownership", icon: "ownership", onSelect: rail("ownership") },
          { id: "history", label: "History", icon: "history", onSelect: rail("history") },
          { id: "explore", label: "Explore", icon: "explore", onSelect: rail("explore") },
          { id: "questions", label: "Questions", icon: "questions", onSelect: rail("questions") },
          { id: "ingest", label: "Ingest Studio", icon: "ingest", onSelect: rail("ingest") },
          // ADR-111 Amendment 3: the Superset boards, drawn inside the Glass.
          { id: "dashboards", label: "Dashboards", icon: "dashboards", onSelect: rail("dashboards") },
          // ADR-110 Amendment 1: the Admin area, as `App.tsx` offers it to an administrator.
          { id: "admin", label: "Admin", icon: "admin", onSelect: rail("admin") },
        ]}
      />
      {wantsCanvas ? (
        <main style={{ flex: 1, position: "relative" }} aria-label="Canvas">
          <GlassCanvas
            graph={workingSet.graph}
            store={workingSet.store}
            ontology={canvasOntology}
            edgeTypes={CANVAS_SCHEMA.edge_types}
            entityTypes={CANVAS_SCHEMA.entity_types}
            investigationId="inv-1"
            apiBaseUrl="http://top-bar.invalid"
            bearerToken="unused"
          />
        </main>
      ) : (
        <main style={{ flex: 1 }} aria-label="Canvas stand-in" />
      )}
    </div>
  </div>,
);
