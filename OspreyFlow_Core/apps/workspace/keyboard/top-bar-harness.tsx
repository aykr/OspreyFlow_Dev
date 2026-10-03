// The Glass's top bar on its own (ADR-065): the case menu, the search box with its Filters icon,
// the view buttons, and the account menu, in the same `app-header` the real `App.tsx` renders.
// `fetch` answers the case list; the outcomes are exposed on `window.__TOPBAR__` for the spec.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { AppSwitcher } from "../src/AppSwitcher";
import { AccountMenu } from "../src/auth/AccountMenu";
import { ThemeToggle } from "../src/theme/ThemeToggle";
import { Button } from "../src/design/primitives/Button";
import { CaseSwitcher } from "../src/investigation/CaseSwitcher";
import { GlobalSearch } from "../src/search/GlobalSearch";

declare global {
  interface Window {
    __TOPBAR__?: { opened: string | null; browsed: boolean; signedOut: boolean };
  }
}

window.__TOPBAR__ = { opened: null, browsed: false, signedOut: false };

const CASES = [
  { id: "c1", name: "Enron corpus (real data, this machine only)", level: "author", created_at: "2026-09-29T09:00:00Z", created_by: "a" },
  { id: "c2", name: "PaySim mobile money (internal)", level: "viewer", created_at: "2026-09-28T09:00:00Z", created_by: "b" },
];
window.fetch = (async () => ({ ok: true, status: 200, json: async () => CASES })) as unknown as typeof fetch;

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <header className="app-header">
    <AppSwitcher app="glass" onChange={() => undefined} />
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
    <div style={{ flex: "1 1 120px", minWidth: 0, maxWidth: 420 }}>
      <GlobalSearch apiBaseUrl="http://top-bar.invalid" bearerToken="unused" entityTypes={["Person", "Endpoint"]} onSelect={() => undefined} />
    </div>
    <Button aria-pressed>Graph</Button>
    <Button>Map</Button>
    <Button>Watches</Button>
    {/* Stands in for the resolution slider ("Balanced"), which needs a server. About its width. */}
    <span style={{ width: 170 }} aria-hidden="true" />
    <Button>Export ⚙</Button>
    <Button>History</Button>
    <div className="app-header__account" style={{ display: "flex", alignItems: "center", gap: "var(--sp-8)" }}>
      <ThemeToggle />
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
    </div>
  </header>,
);
