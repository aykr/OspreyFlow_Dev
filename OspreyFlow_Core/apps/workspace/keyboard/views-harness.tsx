// Case views keyboard harness (ADR-144; the owner's ruling of 8 November 2026, Amendment 2): the Cases
// drawer's *Views in this case* and the cases list with their views, the *Save as a view* form, and
// the case line over an opened saved view (ADR-145 Amendment 19: no strip). `?show=way-back`: the case line's *Saved
// views (n)*, a saved view opened from its panel as `App.tsx`'s `openLens` does, said on the line, and *Back to the
// whole case*. `?details=open` (with `show=lens` or `show=merged`) opens the line's *Details*; `&notes=open` its notes. The Conduit is a stand-in kept here, so that the axe scan of every
// harness (`a11y/every-harness.spec.ts`) sees the panel filled: it answers each reader as the store
// does, Alice's private view to Alice alone (`?as=bob` reads as another member of the case). What was
// sent and what was opened are on `window.__VIEWS__`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { Drawer } from "../src/design/primitives/Drawer";
import { CaseList } from "../src/investigation/CaseList";
import { CaseSwitcher } from "../src/investigation/CaseSwitcher";
import { SaveViewForm } from "../src/views/SaveViewForm";
import type { CaseState } from "../src/views/SavedViewOnTheLine";
import { ContextBanner, focusSavedViewsButton } from "../src/shell/ContextBanner";
import { ViewsPanel } from "../src/views/ViewsPanel";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __VIEWS__?: {
      sent: { method: string; path: string }[];
      opened: string | null;
      openedView: { caseId: string; viewId: string } | null;
      saved: string | null;
      back: boolean;
    };
  }
}

const params = new URLSearchParams(window.location.search);
const reader = params.get("as") ?? "alice";
const at = "2026-11-08T10:00:00Z";
const CASES = [
  { id: "c1", name: "Operation Ledger (synthetic demo)", level: "author", created_at: at, created_by: "alice" },
  { id: "c2", name: "HMP (synthetic demo)", level: "editor", created_at: at, created_by: "alice" },
];
const views: Record<string, { id: string; case_id: string; name: string; created_by: string; created_at: string; shared: boolean; chosen: number }[]> = {
  c1: [
    // `?long=1`: a view with a long name, which must wrap beside its tag rather than push it out (ADR-145 Amendment 14).
    { id: "v-private", case_id: "c1", name: params.get("long") === "1" ? "Alice's own: every payment between the three Ledger accounts in March and April" : "Alice's own",
      created_by: "alice", created_at: at, shared: false, chosen: 3 },
    { id: "v-shared", case_id: "c1", name: "Payments in March", created_by: "alice", created_at: at, shared: true, chosen: 4 },
  ],
  c2: [{ id: "v-hmp", case_id: "c2", name: "Visits this week", created_by: "alice", created_at: at, shared: true, chosen: 2 }],
};

window.__VIEWS__ = { sent: [], opened: null, openedView: null, saved: null, back: false };
const json = (status: number, body: unknown) =>
  new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

window.fetch = async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const path = new URL(String(input)).pathname;
  const method = init.method ?? "GET";
  window.__VIEWS__!.sent.push({ method, path });
  if (path === "/v1/investigations") return json(200, CASES);
  const listed = /^\/v1\/investigations\/([^/]+)\/views$/.exec(path);
  // `?empty=1`: a case with no views yet (the menu's empty state).
  if (listed && method === "GET" && params.get("empty") === "1") return json(200, []);
  if (listed && method === "GET") {
    // The store's own rule: a private view is its creator's alone.
    return json(200, (views[listed[1]!] ?? []).filter((v) => v.shared || v.created_by === reader));
  }
  const one = /^\/v1\/investigations\/([^/]+)\/views\/([^/]+)(\/share)?$/.exec(path);
  if (one) {
    const [, caseId, viewId, share] = one;
    const view = (views[caseId!] ?? []).find((v) => v.id === viewId && (v.shared || v.created_by === reader));
    if (!view) return json(404, { error: "view_not_found" });
    if (method === "GET") return json(200, view);
    if (view.created_by !== reader) return json(403, { error: "not_the_views_creator" });
    if (share) {
      view.shared = true;
      return json(200, view);
    }
    views[caseId!] = views[caseId!]!.filter((v) => v.id !== viewId);
    return json(204, null);
  }
  return json(404, {});
};

await applyHarnessBrand();

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");
const show = params.get("show");

// `?asking=delete`: the panel drawn asking "Delete this view?", for the axe scan and the drawer-fit case (`views.spec.ts`).
if (params.get("asking") === "delete") {
  const ask = () => {
    const button = document.querySelector<HTMLButtonElement>('button[aria-label="Delete Alice\'s own"]');
    if (button) button.click();
    else requestAnimationFrame(ask);
  };
  requestAnimationFrame(ask);
}

/** The way back to the whole case (`?show=way-back`, ADR-145 Amendment 19), as `App.tsx` draws it: the case line with
 * *Saved views (n)* and what is open, "Whole case" or "Saved view: ‹name›" with its tag, *Details* and *Back to the
 * whole case*; the saved views panel it opens (the real one). Opening a saved view takes focus to its name on the line;
 * the back link puts it on *Saved views* again. */
function WayBack() {
  const [lens, setLens] = useState<{ id: string; name: string; shared: boolean } | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  return (
    // The window's width, as App's line has it, so the line folds as it does there (Amendment 19 decision 4).
    <div style={{ width: "calc(100vw - 2 * var(--sp-12))", display: "grid", gap: "var(--sp-16)" }}>
      <ContextBanner
        place="glass"
        // The real switcher, as `App.tsx` passes it, so the line's fold reaches it (Amendment 19 decision 4, step 4).
        caseSwitcher={<CaseSwitcher apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" currentId="c1" onOpen={() => undefined} onBrowse={() => undefined} />}
        datasets={["Ledger payments (synthetic)"]}
        crossLink={{ label: "Open this case's data in the Ingest Studio ↗", shortLabel: "Open in the Ingest Studio ↗", onFollow: () => undefined }}
        onViews={() => setPanelOpen((open) => !open)}
        viewsOpen={panelOpen}
        savedViews={views.c1!.length}
        caseState={
          lens
            ? {
                id: lens.id,
                name: lens.name,
                shared: lens.shared,
                missing: 0,
                onBack: () => {
                  window.__VIEWS__!.back = true;
                  setLens(null);
                  requestAnimationFrame(() => focusSavedViewsButton());
                },
              }
            : "whole"
        }
      />
      {/* What the line sits over: its top must not move when a saved view opens or closes (Amendment 19 decision 1). */}
      <main aria-label="Canvas stand-in" style={{ height: 240, background: "var(--surface-sunken)" }} />
      {panelOpen && (
        <ViewsPanel
          apiBaseUrl="http://keyboard-test.invalid"
          bearerToken="unused"
          caseId="c1"
          me={reader}
          openViewId={lens?.id ?? null}
          onOpen={(view) => {
            window.__VIEWS__!.opened = view.id;
            setPanelOpen(false);
            setLens({ id: view.id, name: view.name, shared: view.shared });
          }}
        />
      )}
    </div>
  );
}

/** A saved view open, said on the case line as `App.tsx` draws it, over a stand-in canvas so *Details* has somewhere to
 * open over. `?details=open` presses *Details*; `&notes=open` then its notes (for the axe scan of the open list). */
function OnTheLine({ state }: { state: CaseState }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 480 }}>
      <ContextBanner place="glass" caseSwitcher={<span className="value">Operation Ledger (synthetic demo)</span>} onViews={() => undefined} savedViews={2} caseState={state} />
      <main aria-label="Canvas stand-in" style={{ flex: 1, background: "var(--surface-sunken)" }} />
    </div>
  );
}
const pressWhenDrawn = (name: string, then?: () => void) => {
  const go = () => {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.replace("▾", "").trim() === name);
    if (!button) return void requestAnimationFrame(go);
    button.click();
    then?.();
  };
  requestAnimationFrame(go);
};
if (params.get("details") === "open" || params.get("notes") === "open")
  pressWhenDrawn("Details", () => (params.get("notes") === "open" ? pressWhenDrawn("Notes from the drawing (2)") : undefined));

const listed = (
  <>
    <ViewsPanel
      apiBaseUrl="http://keyboard-test.invalid"
      bearerToken="unused"
      caseId="c1"
      me={reader}
      onOpen={(view) => (window.__VIEWS__!.opened = view.id)}
    />
    <CaseList
      apiBaseUrl="http://keyboard-test.invalid"
      bearerToken="unused"
      currentId="c1"
      onOpen={() => undefined}
      onOpenView={(caseId, view) => (window.__VIEWS__!.openedView = { caseId, viewId: view.id })}
    />
  </>
);

createRoot(container).render(
  <div style={{ display: "grid", gap: "var(--sp-16)", padding: "var(--sp-12)", background: "var(--surface-panel)" }}>
    {show === "way-back" && <WayBack />}
    {show === "lens" && <OnTheLine state={{ id: "v-shared", name: "Payments in March", shared: true, missing: 2, onBack: () => (window.__VIEWS__!.back = true) }} />}
    {/* ADR-143 Amendment 2 decision 7 (L3.9): a merged drawing's view, with its notes in the line's *Details*. */}
    {show === "merged" && (
      <OnTheLine
        state={{
          id: "v-night", name: "Night visits", shared: false, missing: 0, onBack: () => (window.__VIEWS__!.back = true),
          annotations: [
            { element_id: "e-1", kind: "node", label: "Mercer", marking: "OFFICIAL", grading: "B21", source_note: "Wing officer report, 4 Nov",
              words: "Drawn by A. Field, merged as load promotion-night-1", merged: true },
            { element_id: "e-2", kind: "node", label: "Night boat", marking: "OFFICIAL", grading: "C32", source_note: "Harbour log",
              words: "Drawn by A. Field, not merged: it stays in the drawing, read-only", merged: false },
          ],
        }}  // prettier-ignore
      />
    )}
    {show === "form" && (
      <SaveViewForm
        count={3}
        defaultName="Selection of 3 nodes"
        onSave={async (name) => {
          window.__VIEWS__!.saved = name;
          return null;
        }}
        onCancel={() => undefined}
      />
    )}
    {show === "way-back" ? null : params.get("in") === "drawer" ? (
      // ADR-145 Amendment 14 decision 1: `?in=drawer` draws the panel and the list as `App.tsx`'s Cases drawer
      // does, in the real 360 px drawer, where the owner saw Open cover the Private tag.
      <Drawer open onClose={() => undefined} title="Cases">
        <div className="drawer-stack">
          {listed}
        </div>
      </Drawer>
    ) : (
      listed
    )}
  </div>,
);
