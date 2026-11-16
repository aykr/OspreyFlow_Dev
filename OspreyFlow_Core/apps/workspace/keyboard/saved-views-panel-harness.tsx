// The saved views panel (ADR-145 Amendment 17, the owner's exception of 14 November 2026), as `App.tsx` draws it
// from the case line's *Saved views*: the real `ViewsPanel` in the real drawer, titled *Saved views*, the views list
// alone. The case line itself is case's (`views-harness.tsx`, `ContextBanner`); here a plain button stands in for its
// *Saved views* (`data-saved-views-button`), the drawer's focus returning to it as the App's does. The App's lens is
// a line of state: which saved view is open, or the whole case. The Conduit answers the list as it answers a reader:
// each view's `first_item` the first chosen node they may see, `null` for none. `?open=<id>` opens that saved view
// first; `?brand=govuk` the GOV.UK look. What was opened is on `window.__SAVED_VIEWS__`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { Drawer } from "../src/design/primitives/Drawer";
import { ViewsPanel } from "../src/views/ViewsPanel";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __SAVED_VIEWS__?: { opened: string[] };
  }
}

const params = new URLSearchParams(window.location.search);
const VIEWS = [
  { id: "v-3", case_id: "c1", name: "Selection of 3 nodes", created_by: "alice", created_at: "2026-11-14T12:01:00Z", shared: false, chosen: 3, first_item: "Tarbuck, Kyle" },
  { id: "v-2", case_id: "c1", name: "Selection of 2 nodes", created_by: "alice", created_at: "2026-11-14T11:40:00Z", shared: false, chosen: 2, first_item: "Vance, Callum" },
  { id: "v-hidden", case_id: "c1", name: "Selection of 2 nodes", created_by: "bob", created_at: "2026-11-13T09:15:00Z", shared: true, chosen: 2, first_item: null },
  { id: "v-named", case_id: "c1", name: "Numbers of interest", created_by: "alice", created_at: "2026-11-12T16:20:00Z", shared: true, chosen: 3, first_item: "PIN-Z2486" },
];
window.__SAVED_VIEWS__ = { opened: [] };
window.fetch = async (input: RequestInfo | URL) => {
  const path = new URL(String(input), window.location.origin).pathname;
  if (path === "/v1/investigations/c1/views") return new Response(JSON.stringify(VIEWS), { status: 200 });
  return new Response("{}", { status: 404 });
};

await applyHarnessBrand();

function Harness() {
  const [panelOpen, setPanelOpen] = useState(true);
  const [openViewId, setOpenViewId] = useState<string | null>(params.get("open"));
  const opened = VIEWS.find((v) => v.id === openViewId);
  return (
    <div>
      <p data-harness-only="">
        <button type="button" data-saved-views-button="" aria-expanded={panelOpen} onClick={() => setPanelOpen((o) => !o)}>
          Saved views ({VIEWS.length})
        </button>{" "}
        <span id="lens">{opened ? `Saved view: ${opened.name}` : "Whole case"}</span>
      </p>
      <Drawer
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        title="Saved views"
        returnFocusTo={() => document.querySelector<HTMLElement>("[data-saved-views-button]")}
      >
        <div className="drawer-stack">
          <ViewsPanel
            apiBaseUrl={window.location.origin}
            bearerToken="harness"
            caseId="c1"
            me="alice"
            openViewId={openViewId}
            takeFocus
            onOpenWholeCase={() => {
              window.__SAVED_VIEWS__!.opened.push("whole-case");
              setPanelOpen(false);
              setOpenViewId(null);
            }}
            onOpen={(view) => {
              window.__SAVED_VIEWS__!.opened.push(view.id);
              setPanelOpen(false);
              setOpenViewId(view.id);
            }}
          />
        </div>
      </Drawer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
