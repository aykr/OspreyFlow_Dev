// The workspace shell's top (ADR-065, ADR-097 step 1): the classification strip, the real `TopBar`
// `App.tsx` renders (the mark, the case menu, the search box with its Filters icon, the view switch,
// Export and the account menu), and the left rail beside it. `fetch` answers the case list; the
// outcomes are exposed on `window.__TOPBAR__` for the specs.
import { useCallback, useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import { applyHarnessBrand } from "./brandHarness";
import "../src/design/primitives.css";
import { ClassificationStrip } from "../src/shell/ClassificationStrip";
import { LeftRail } from "../src/shell/LeftRail";
import { BuildAReportLink, TopBar } from "../src/shell/TopBar";
import { AccountMenu } from "../src/auth/AccountMenu";
import { Button } from "../src/design/primitives/Button";
import { CaseSwitcher } from "../src/investigation/CaseSwitcher";
import { GlobalSearch } from "../src/search/GlobalSearch";
import { GlassCanvas } from "../src/canvas/GlassCanvas";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import { guideUrl } from "../src/home/guides";
import { MORE_VIEWS, ON_THE_RAIL, RAIL_LABELS, splitRail, splitViews, VIEW_LABELS, VIEW_SWITCH } from "../src/shell/railLayout";
import type { RailEntry } from "../src/rights/visibility";

// The rail and the view switch as `App.tsx` lays them out (the owner's navigation decision, ADR-145 Amendment 15).
const RAIL_ENTRIES: readonly RailEntry[] = ON_THE_RAIL;
const SWITCHED = splitViews(
  [...VIEW_SWITCH, ...MORE_VIEWS].map((id) => ({ id, label: VIEW_LABELS[id], pressed: id === "graph", onSelect: () => window.__TOPBAR__!.views.push(id) })),
);
import { useHelpKey, WorkspaceWelcome } from "../src/welcome/WorkspaceWelcome";
import type { OntologySchema } from "../../../packages/schemas/generated";

declare global {
  interface Window {
    /** With `?canvas=1`: whether the real canvas holds a node, and how many it holds. */
    __TOPBAR_CANVAS__?: { hasNode: (id: string) => boolean; count: () => number };
    __TOPBAR__?: { opened: string | null; browsed: boolean; signedOut: boolean; rail: string[]; views: string[]; help?: number; guide?: number };
  }
}

window.__TOPBAR__ = { opened: null, browsed: false, signedOut: false, rail: [], views: [] };

// `?long=1`: the current case has a long name and reads one dataset with a long name, as the Prison
// Intelligence demo does, so the bar carries the case and its scope badge at their widest.
const wantsLong = new URLSearchParams(window.location.search).get("long") === "1";
const CASES = [
  { id: "c1", name: "Enron corpus (real data, this machine only)", level: "author", created_at: "2026-09-29T09:00:00Z", created_by: "a" },
  { id: "c2", name: "PaySim mobile money (internal)", level: "viewer", created_at: "2026-09-28T09:00:00Z", created_by: "b" },
  ...(wantsLong
    ? [{ id: "c3", name: "Prison Intelligence Dataset (synthetic demo)", level: "editor", created_at: "2026-10-27T09:00:00Z", created_by: "c", datasets: ["Prison Intelligence Dataset (synthetic)"] }]
    : []),
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

await applyHarnessBrand();

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

const rail = (id: string) => () => window.__TOPBAR__!.rail.push(id);

/** The rail as `App.tsx` splits it (ADR-145 Amendment 12), and its Help toggling the real keys panel,
 * as `App.tsx` does: Help or `?` opens it, again closes it, and Esc or × closes it. */
function RailWithHelp() {
  // `?help=1`: the keys panel open from the start, for the scans (`a11y/every-harness.spec.ts`).
  const [helpOpen, setHelpOpen] = useState(new URLSearchParams(window.location.search).get("help") === "1");
  const toggle = useCallback(() => setHelpOpen((open) => !open), []);
  useHelpKey(toggle);
  return (
    <>
      <LeftRail
        onHelp={() => {
          window.__TOPBAR__!.help = (window.__TOPBAR__!.help ?? 0) + 1;
          toggle();
        }}
        // Split and ordered as `App.tsx` does it (`shell/railLayout.ts`), so these cases see its layout.
        {...splitRail(RAIL_ENTRIES.map((id) => ({ id, label: RAIL_LABELS[id], icon: id, onSelect: rail(id) })))}
      />
      {/* Beside the rail, never over it, as `App.tsx` places it in the column the views share. */}
      {helpOpen && (
        <div style={{ position: "relative", width: 0 }}>
        <WorkspaceWelcome
          apiBaseUrl="http://top-bar.invalid"
          bearerToken="unused"
          investigationId="inv-1"
          nodeCount={0}
          onRestored={() => undefined}
          onClose={() => setHelpOpen(false)}
          takeFocus
          guide={{
            href: guideUrl("http://top-bar.invalid", "user"),
            open: () => {
              window.__TOPBAR__!.guide = (window.__TOPBAR__!.guide ?? 0) + 1;
              return Promise.resolve(null);
            },
          }}
        />
        </div>
      )}
    </>
  );
}

createRoot(container).render(
  <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
    <ClassificationStrip marking="OFFICIAL" />
    <TopBar
      app="glass"
      caseSwitcher={
        <CaseSwitcher
          apiBaseUrl="http://top-bar.invalid"
          bearerToken="unused"
          currentId={wantsLong ? "c3" : "c1"}
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
      views={SWITCHED.main}
      // ADR-145 Amendment 15: Matrix, Figures, Ownership and Connection strength under More views, as `App.tsx` offers them.
      moreViews={SWITCHED.more}
      // `?reports=1`: a builder on a deployment with Superset, *Build a report* beside Reports as `App.tsx` draws it
      // (ADR-145 Amendment 15); the address is a stand-in, never followed.
      besideViews={new URLSearchParams(window.location.search).get("reports") === "1" ? <BuildAReportLink href="https://bi.example.invalid" /> : undefined}
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
      <RailWithHelp />
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
