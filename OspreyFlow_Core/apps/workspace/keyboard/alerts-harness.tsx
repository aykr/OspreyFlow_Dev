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
    __ALERTS__?: { canvasNodeIds: string[] | null };
  }
}

window.__ALERTS__ = { canvasNodeIds: null };

createRoot(document.getElementById("root")!).render(
  <AlertsPlace
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    accountId="analyst-1"
    isAdministrator={false}
    onCanvas={(_outcome, nodeIds) => {
      window.__ALERTS__!.canvasNodeIds = nodeIds;
    }}
  />,
);
