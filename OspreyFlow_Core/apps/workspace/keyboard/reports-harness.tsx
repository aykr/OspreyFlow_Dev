// The Reports view's keyboard harness (ADR-111, `CLAUDE.md` rule 13): its own surface, its own
// registry (`REPORTS_ACTIONS`). Every call is intercepted by `reports.spec.ts`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { ReportsPlace } from "../src/reports/ReportsPlace";

declare global {
  interface Window {
    __EMBEDDED__?: { id: string; domain: string }[];
  }
}
window.__EMBEDDED__ = [];

createRoot(document.getElementById("root")!).render(
  <ReportsPlace
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    canDownload
    // The Superset frame itself is Superset's; the harness records what it was asked to mount.
    embed={async ({ id, supersetDomain }) => {
      window.__EMBEDDED__!.push({ id, domain: supersetDomain });
    }}
  />,
);
