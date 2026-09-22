// Watch-panels keyboard harness — `CLAUDE.md` rule 13's "or its equivalent for a new surface":
// hotlists/monitors/the alert inbox are the fourth keyboard-driven surface
// (`keyboard/harness.tsx`'s own `CANVAS_ACTIONS`, `metrics-panel-harness.tsx`'s own
// `METRICS_PANEL_ACTIONS`, `query-builder-harness.tsx`'s own `QUERY_BUILDER_ACTIONS`), so it gets
// its own harness rather than folding into any of them. Renders `HotlistPanel`, `MonitorPanel` and
// `AlertInbox` together, the same shape they are mounted together under `App.tsx`'s `"watches"`
// view. `POST/GET /v1/hotlists`, `POST/GET /v1/monitors`, `GET /v1/patterns`, `GET /v1/alerts` and
// `POST /v1/alerts/{id}/jump` are intercepted by `watch-panels.spec.ts` via `page.route` — the
// same "real network call, mocked at the transport, not the component" shape
// `query-builder.spec.ts` already uses.
//
// `AlertInbox`'s own `onOpenInvestigation` callback has no canvas/App.tsx counterpart in this
// harness (nothing here drives a working set) — exposed instead as `window.__WATCH_HARNESS__` so a
// spec case can prove the callback actually fires with the real investigation id, the same
// `window.__KEYBOARD__` shape `keyboard/harness.tsx` already uses for `GlassCanvas`'s own
// focus/selection callbacks.
import { createRoot } from "react-dom/client";

import "../../../docs/design/tokens.css";
import "../src/design/primitives.css";
import { AlertInbox } from "../src/watches/AlertInbox";
import { HotlistPanel } from "../src/watches/HotlistPanel";
import { MonitorPanel } from "../src/watches/MonitorPanel";

declare global {
  interface Window {
    __WATCH_HARNESS__?: { openedInvestigationId: string | null };
  }
}

window.__WATCH_HARNESS__ = { openedInvestigationId: null };

function Harness() {
  return (
    <div style={{ width: 480, display: "flex", flexDirection: "column", gap: 16 }}>
      <HotlistPanel apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" />
      <MonitorPanel apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" />
      <AlertInbox
        apiBaseUrl="http://keyboard-test.invalid"
        bearerToken="unused"
        onOpenInvestigation={(investigationId) => {
          window.__WATCH_HARNESS__!.openedInvestigationId = investigationId;
        }}
      />
    </div>
  );
}

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

createRoot(container).render(<Harness />);
