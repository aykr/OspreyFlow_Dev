// The Reports view's keyboard harness (ADR-111, `CLAUDE.md` rule 13): its own surface, its own
// registry (`REPORTS_ACTIONS`). Every call is intercepted by `reports.spec.ts`.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { ReportsView } from "../src/reports/ReportsView";

createRoot(document.getElementById("root")!).render(
  <ReportsView apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" investigationId="inv-1" />,
);
