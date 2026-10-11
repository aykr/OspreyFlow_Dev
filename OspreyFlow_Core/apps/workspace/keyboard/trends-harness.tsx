// The Trends tab's keyboard harness (ADR-113 stage 5, `CLAUDE.md` rule 13): the Reports place with
// every right assumed, so the Trends tab is there; `trends.spec.ts` intercepts every call.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { ReportsPlace } from "../src/reports/ReportsPlace";

createRoot(document.getElementById("root")!).render(
  <ReportsPlace apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" investigationId="inv-1" canDownload rights={null} />,
);
