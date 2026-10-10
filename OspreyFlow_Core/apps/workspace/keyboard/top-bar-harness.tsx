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

declare global {
  interface Window {
    __TOPBAR__?: { opened: string | null; browsed: boolean; signedOut: boolean; rail: string[] };
  }
}

window.__TOPBAR__ = { opened: null, browsed: false, signedOut: false, rail: [] };

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
window.fetch = (async (url: string) => {
  const body = String(url).endsWith("/suggest") ? { nodes: SUGGESTIONS, more: true } : CASES;
  return { ok: true, status: 200, json: async () => body };
}) as unknown as typeof fetch;

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
        <GlobalSearch apiBaseUrl="http://top-bar.invalid" bearerToken="unused" investigationId="inv-1" entityTypes={["Person", "Endpoint"]} onSelect={() => undefined} />
      }
      views={[
        { id: "graph", label: "Graph", pressed: true, onSelect: () => undefined },
        { id: "map", label: "Map", pressed: false, onSelect: () => undefined },
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
        items={[
          { id: "cases", label: "Cases", icon: "cases", onSelect: rail("cases") },
          { id: "watches", label: "Watches", icon: "watches", onSelect: rail("watches") },
          { id: "alerts", label: "Alerts", icon: "alerts", onSelect: rail("alerts") },
          { id: "ownership", label: "Ownership", icon: "ownership", onSelect: rail("ownership") },
          { id: "history", label: "History", icon: "history", onSelect: rail("history") },
          { id: "explore", label: "Explore", icon: "explore", onSelect: rail("explore") },
          { id: "questions", label: "Questions", icon: "questions", onSelect: rail("questions") },
          { id: "ingest", label: "Ingest Studio", icon: "ingest", onSelect: rail("ingest") },
        ]}
      />
      <main style={{ flex: 1 }} aria-label="Canvas stand-in" />
    </div>
  </div>,
);
