// Case views keyboard harness (ADR-144; the owner's ruling of 8 November 2026, Amendment 2): the Cases
// drawer's *Views in this case* and the cases list with their views, the *Save as a view* form, and
// the banner over an opened view. `?show=menu` (Amendment 3): the graph's *Views ▾*, a view chosen there
// opening the lens banner as `App.tsx`'s `openLens` does, and *Back to the case* closing it. The Conduit is a stand-in kept here, so that the axe scan of every
// harness (`a11y/every-harness.spec.ts`) sees the panel filled: it answers each reader as the store
// does, Alice's private view to Alice alone (`?as=bob` reads as another member of the case). What was
// sent and what was opened are on `window.__VIEWS__`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { CaseList } from "../src/investigation/CaseList";
import { SaveViewForm } from "../src/views/SaveViewForm";
import { ViewLensBanner } from "../src/views/ViewLensBanner";
import { ViewsMenu } from "../src/views/ViewsMenu";
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
    { id: "v-private", case_id: "c1", name: "Alice's own", created_by: "alice", created_at: at, shared: false, chosen: 3 },
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

// `?asking=delete`: the panel drawn asking "Delete this view?", for the axe scan; no spec uses it.
if (params.get("asking") === "delete") {
  const ask = () => {
    const button = document.querySelector<HTMLButtonElement>('button[aria-label="Delete Alice\'s own"]');
    if (button) button.click();
    else requestAnimationFrame(ask);
  };
  requestAnimationFrame(ask);
}

/** The graph's *Views ▾* in its toolbar's View group, and the lens a chosen view opens (`?show=menu`). */
function ByTheGraph() {
  const [lens, setLens] = useState<{ id: string; name: string; shared: boolean } | null>(null);
  return (
    <>
      {lens && (
        <ViewLensBanner
          name={lens.name}
          shared={lens.shared}
          missing={0}
          onBack={() => {
            window.__VIEWS__!.back = true;
            setLens(null);
          }}
        />
      )}
      <div role="toolbar" aria-label="Canvas tools" className="canvas-toolbar">
        <div role="group" aria-label="View" className="canvas-toolbar__group canvas-toolbar__group--end">
          <ViewsMenu
            apiBaseUrl="http://keyboard-test.invalid"
            bearerToken="unused"
            caseId="c1"
            openViewId={lens?.id ?? null}
            onOpen={(view) => {
              window.__VIEWS__!.opened = view.id;
              setLens({ id: view.id, name: view.name, shared: view.shared });
            }}
          />
        </div>
      </div>
      {/* Room under the toolbar for the menu's panel, laid over the canvas in the Glass. */}
      <div style={{ height: 160 }} />
    </>
  );
}

// `?show=menu&open=1`: the menu drawn open, for the axe scan.
if (show === "menu" && params.get("open") === "1") {
  const press = () => {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.startsWith("Views"));
    if (button) button.click();
    else requestAnimationFrame(press);
  };
  requestAnimationFrame(press);
}

createRoot(container).render(
  <div style={{ display: "grid", gap: "var(--sp-16)", padding: "var(--sp-12)", background: "var(--surface-panel)" }}>
    {show === "menu" && <ByTheGraph />}
    {show === "lens" && (
      <ViewLensBanner name="Payments in March" shared missing={2} onBack={() => (window.__VIEWS__!.back = true)} />
    )}
    {/* ADR-143 Amendment 2 decision 7 (L3.9): a merged drawing's view, with its notes. */}
    {show === "merged" && (
      <ViewLensBanner
        notesOpen={params.get("notes") === "open"}
        name="Night visits"
        shared={false}
        missing={0}
        onBack={() => (window.__VIEWS__!.back = true)}
        annotations={[
          { element_id: "e-1", kind: "node", label: "Mercer", marking: "OFFICIAL", grading: "B21", source_note: "Wing officer report, 4 Nov",
            words: "Drawn by A. Field, merged as load promotion-night-1", merged: true },
          { element_id: "e-2", kind: "node", label: "Night boat", marking: "OFFICIAL", grading: "C32", source_note: "Harbour log",
            words: "Drawn by A. Field, not merged: it stays in the drawing, read-only", merged: false },
        ]}  // prettier-ignore
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
  </div>,
);
