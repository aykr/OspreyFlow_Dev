// The Ownership place's keyboard harness (ADR-109 phase C, `CLAUDE.md` rule 13): its own surface,
// its own registry (`OWNERSHIP_ACTIONS`). Every call is intercepted by `ownership.spec.ts`; what it
// hands the canvas is recorded on `window.__OWNERSHIP__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { OwnershipPlace } from "../src/ownership/OwnershipPlace";

declare global {
  interface Window {
    __OWNERSHIP__?: { canvasNodeIds: string[] | null };
  }
}

window.__OWNERSHIP__ = { canvasNodeIds: null };

createRoot(document.getElementById("root")!).render(
  <OwnershipPlace
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    onCanvas={(_outcome, nodeIds) => {
      window.__OWNERSHIP__!.canvasNodeIds = nodeIds;
    }}
  />,
);
