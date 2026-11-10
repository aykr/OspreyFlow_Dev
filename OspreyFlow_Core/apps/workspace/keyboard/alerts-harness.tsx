// The alerts' keyboard harness (ADR-109 phase B, `CLAUDE.md` rule 13), with its own walkthrough
// registry (`ALERTS_ACTIONS`). Renders Rules and Monitoring (`RulesPlace`, ADR-146 decision 2) as
// `App.tsx` mounts it; every
// call it makes is intercepted by `alerts.spec.ts` at the transport. What it hands the canvas is
// recorded on `window.__ALERTS__`, since nothing here draws a working set.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { RulesPlace } from "../src/alerts/RulesPlace";

declare global {
  interface Window {
    __ALERTS__?: { canvasNodeIds: string[] | null; addressed: (string | null)[] };
  }
}

window.__ALERTS__ = { canvasNodeIds: null, addressed: [] };

createRoot(document.getElementById("root")!).render(
  <RulesPlace
    canMakeLive
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    // ADR-133 stage (d): `?account=` signs in as another member (a second person), `?admin=1` as an
    // administrator, who approves a whole-deployment rule's change.
    accountId={new URLSearchParams(window.location.search).get("account") ?? "analyst-1"}
    isAdministrator={new URLSearchParams(window.location.search).get("admin") === "1"}
    // ADR-133 stage (c): `?lists=manage` renders the Lists tab for whoever may load screening lists.
    canManageLists={new URLSearchParams(window.location.search).get("lists") === "manage"}
    onCanvas={(_outcome, nodeIds) => {
      window.__ALERTS__!.canvasNodeIds = nodeIds;
    }}
    // ADR-146 decision 6: an alert opened here is given its address (`App.tsx` pushes it).
    onOpenAlert={(id) => {
      window.__ALERTS__!.addressed.push(id);
    }}
  />,
);
