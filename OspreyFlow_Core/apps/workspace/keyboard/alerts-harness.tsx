// The Alerts place's keyboard harness (ADR-109 phase B, `CLAUDE.md` rule 13): a new surface with its
// own walkthrough registry (`ALERTS_ACTIONS`). Renders `AlertsPlace` as `App.tsx` mounts it; every
// call it makes is intercepted by `alerts.spec.ts` at the transport. What it hands the canvas is
// recorded on `window.__ALERTS__`, since nothing here draws a working set.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { AlertsPlace } from "../src/alerts/AlertsPlace";

declare global {
  interface Window {
    __ALERTS__?: { canvasNodeIds: string[] | null; openedInvestigationId?: string };
  }
}

window.__ALERTS__ = { canvasNodeIds: null };

createRoot(document.getElementById("root")!).render(
  <AlertsPlace
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
    // The owner's answer of 1 November 2026: the alert inbox's jump, from the Watches tab.
    onOpenInvestigation={(id) => {
      window.__ALERTS__!.openedInvestigationId = id;
    }}
  />,
);
