// The Inspector's Emails section (ADR-089) on its own, the way `link-notes-harness.tsx` mounts the
// notes: `link-events.spec.ts` intercepts the events route and walks the list by keyboard.
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { LinkEvents } from "../src/inspector/LinkEvents";

declare global {
  interface Window {
    __LINK_EVENTS__?: { deltas: unknown[] };
  }
}
window.__LINK_EVENTS__ = { deltas: [] };

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(
  <LinkEvents
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="inv-1"
    edgeId="e1"
    noun="emails"
    sourceLabel="alice@enron.com"
    targetLabel="bob@enron.com"
    onDelta={(delta) => {
      window.__LINK_EVENTS__!.deltas.push(delta);
    }}
  />,
);
