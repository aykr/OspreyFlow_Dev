// Case access keyboard harness (ADR-052 §9): the Share panel as the Cases drawer renders it.
// `case-access.spec.ts` intercepts the access routes.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { CaseAccessPanel } from "../src/investigation/CaseAccessPanel";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <CaseAccessPanel apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" investigationId="c1" />,
);
