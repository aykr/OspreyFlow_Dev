// The Packs and Published tabs' keyboard harness (ADR-113 stage 5, `CLAUDE.md` rule 13): the Reports
// place with every right assumed. The print step is injected so `packs.spec.ts` can read the very
// document that would have been printed, on `window.__PRINTED__`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { ReportsPlace } from "../src/reports/ReportsPlace";

declare global {
  interface Window {
    __PRINTED__?: string[];
  }
}
window.__PRINTED__ = [];

createRoot(document.getElementById("root")!).render(
  <ReportsPlace
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    canDownload
    rights={null}
    print={(html) => {
      window.__PRINTED__!.push(html);
    }}
  />,
);
