// Link-notes keyboard harness (ADR-075): the Inspector's Notes section for a selected link is a
// keyboard-driven surface of its own, so — as for the Judgements tab
// (`assessment-panel-harness.tsx`) — it gets a small harness and a spec
// (`link-notes.spec.ts`) that intercepts the four routes at the transport. It mounts `LinkNotes`
// directly, the component `Inspector` renders under a selected link.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { LinkNotes } from "../src/inspector/LinkNotes";

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <LinkNotes
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    edgeId="e1"
  />,
);
