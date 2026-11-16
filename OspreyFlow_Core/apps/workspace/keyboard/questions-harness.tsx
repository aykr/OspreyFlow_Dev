// Questions keyboard harness (ADR-098 decision 4): the case's questions to the model, mounted inside
// Ask & Chat's real drawer, or its page with `?form=page`, as `App.tsx` renders them (ADR-145 Amendments 18 and 20), by
// App's own hook. `questions.spec.ts` intercepts the routes at the
// transport; what the panel hands back (a change to the view, a document to open) is exposed on
// `window.__QUESTIONS__`. A chosen `[G-n]` is proved against the real canvas in `harness.html?questions=1`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { AskPage } from "../src/questions/AskPage";
import { QuestionsPanel } from "../src/questions/QuestionsPanel";
import { useAskPage } from "../src/questions/useAskPage";
import { applyHarnessBrand } from "./brandHarness";

// The every-harness axe scan reads this call to scan GOV.UK too (`?brand=govuk`, ADR-132).
await applyHarnessBrand();

declare global {
  interface Window {
    __QUESTIONS__?: {
      deltas: unknown[];
      opened: string | null;
      closed?: number;
      /** `?history=1`: the node ids of the last marker chosen. */
      chosen?: string[];
      /** What the last question asked about, as the panel sent it. */
      scope?: unknown;
      /** v0.6.0 #5: what Show all on graph and Save as a view were handed. */
      shown?: unknown;
      saved?: unknown;
    };
  }
}

window.__QUESTIONS__ = {
  deltas: [],
  opened: null,
  closed: 0,
};

const container = document.getElementById("root");
if (!container) throw new Error("#root not found");

// `?view=1`: the panel asking in a case view, as *Ask the model about these* opens it (ADR-144
// decision 4), until *Ask about the whole case instead*.
const inView = new URLSearchParams(window.location.search).get("view") === "1";
// `?case=1`: Whole case chosen (ADR-098 Amendment 9), its search answering from its fallback, and an
// answer read from the whole case with its sources, for the every-harness axe scan. The routes are
// answered here, since no spec intercepts them.
const wholeCase = new URLSearchParams(window.location.search).get("case") === "1";
if (wholeCase) {
  const read = {
    read_from: "case", documents: 1, documents_without_text: 0, items: 1, links: 0, events: 0, selected: 0,
    first_selected: null, found: 3, passages: 1, counts_exact: false, more: true,
    limited_reason: "Results are limited: the search index cannot be reached.",
  };  // prettier-ignore
  const answered = {
    id: "q-case", author: "analyst-1", author_name: "Demo Analyst", question: "Who paid Kestrel?",
    answer: "Ann Kestrel was paid by the plant [S-1].", citations: [{ document_id: "d-1", title: "Kestrel letter" }],
    candidates: [], unplaced: 0, created_at: "2026-11-14T10:00:00Z", engine: "local", model: "qwen2.5:7b-instruct", read,
    search_citations: [
      { number: 1, label: "[S-1]", name: "KESTREL, Ann", type: "Person", why: "Name is 'Kestrel'", node_ids: ["n-k"] },
      { number: 2, label: "[S-2]", name: "Kestrel invoice", type: "Document", why: "Mentions 'Kestrel'", node_ids: ["d-2"] },
    ],
  };  // prettier-ignore
  const will = { read, engine: "local", engine_label: "This deployment's own model", model: "qwen2.5:7b-instruct", unusable: [], refused: null };
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const body = url.endsWith("/will-read") ? will : init?.method === "POST" ? answered : url.includes("/models/") ? { engines: [] } : [answered];
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  };
}

// `?history=1` (v0.6.0 #3): three questions already asked, the history an accordion: an earlier answer with graph
// facts, one with two proposals still to decide, and the newest, open. For `questions.spec.ts`'s accordion case and
// the every-harness axe scan; the routes are answered here.
const withHistory = new URLSearchParams(window.location.search).get("history") === "1";
if (withHistory) {
  const at = (minute: number) => `2026-11-15T10:${String(minute).padStart(2, "0")}:00Z`;
  const base = { author: "analyst-1", author_name: "Demo Analyst", citations: [], unplaced: 0, engine: "local", model: "qwen2.5:7b-instruct" };
  const history = [
    { ...base, id: "q-1", question: "Who is tied to Dana?", answer: "Rohan is tied to Dana [G-1]; Dana called Callum [G-2].", candidates: [], created_at: at(0),
      graph_citations: [
        { number: 1, label: "[G-1]", about: "SHAH, Rohan – associated with – MERCER, Dana", node_ids: ["n-rohan", "n-dana"], link_ids: ["l-1"] },
        { number: 2, label: "[G-2]", about: "MERCER, Dana – called – PRICE, Callum", node_ids: ["n-dana", "n-callum"], link_ids: ["l-2"] },
      ] },
    { ...base, id: "q-2", question: "Who wrote about the plant?", answer: "Dana Mercer and Eli Ward wrote about it.", created_at: at(5),
      candidates: [
        { id: "c-1", document_id: "d-1", entity_type: "Person", properties: { name: "Dana Mercer" }, confidence: 0.8, status: "pending", model: "qwen" },
        { id: "c-2", document_id: "d-1", entity_type: "Person", properties: { name: "Eli Ward" }, confidence: 0.7, status: "pending", model: "qwen" },
      ] },
    { ...base, id: "q-3", question: "Who called Callum?", answer: "Dana called Callum [G-1].", candidates: [], created_at: at(9),
      graph_citations: [{ number: 1, label: "[G-1]", about: "MERCER, Dana – called – PRICE, Callum", node_ids: ["n-dana", "n-callum"], link_ids: ["l-2"] }] },
  ];  // prettier-ignore
  const read = { read_from: "selection", documents: 0, documents_without_text: 0, items: 1, links: 0, events: 0, selected: 1, first_selected: "MERCER, Dana", found: 0, passages: 0, limited_reason: null, counts_exact: true, more: false };  // prettier-ignore
  const will = { read, engine: "local", engine_label: "This deployment's own model", model: "qwen2.5:7b-instruct", unusable: [], refused: null };
  window.fetch = async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.endsWith("/will-read") ? will : url.includes("/models/") ? { engines: [] } : history;
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  };
}

function Panel() {
  const [view, setView] = useState<{ id: string; name: string } | null>(
    inView ? { id: "v-q", name: "Questions on 2 items" } : null,
  );
  return (
    <QuestionsPanel
    apiBaseUrl="http://keyboard-test.invalid"
    bearerToken="unused"
    investigationId="b1"
    onDelta={(delta) => window.__QUESTIONS__!.deltas.push(delta)}
    onOpenDocument={(id) => {
      window.__QUESTIONS__!.opened = id;
    }}
    selection={{ nodeIds: ["n-dana"], linkIds: [] }}
    view={view}
    onLeaveView={() => setView(null)}
    initialReadFrom={wholeCase ? "case" : undefined}
    // In the history mode a marker can be chosen, so it is reached by Tab (a marker with nowhere to go is disabled).
    onSelectFacts={withHistory ? (citation) => { window.__QUESTIONS__!.chosen = citation.node_ids; } : undefined}
    // v0.6.0 #5: Show all on graph and Save as a view under each answer, as `App.tsx` offers them; what they were
    // handed is kept for a spec, the canvas being `harness.html?questions=1`'s.
    onShowAll={(ids) => (window.__QUESTIONS__!.shown = ids)}
    onSaveAsView={async (ids, name) => {
      window.__QUESTIONS__!.saved = { ids, name };
      return null;
    }}
    />
  );
}

// `?save=1` (with `?case=1`): the answer's *Save as a view* form drawn open, for the every-harness axe scan.
if (new URLSearchParams(window.location.search).get("save") === "1") {
  const press = () => {
    const button = [...document.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Save as a view");
    if (button) button.click();
    else setTimeout(press, 50);
  };
  setTimeout(press, 50);
}

// `?form=page`: open as the page, as the results' Ask line opens it; otherwise the drawer, as the rail opens it (ADR-145
// Amendment 20).
const form = new URLSearchParams(window.location.search).get("form") === "page" ? "page" : "drawer";

function Page() {
  const ask = useAskPage(false, { leave: () => undefined }, form);
  if (!ask.open) return <p>The view.</p>;
  return (
    <AskPage
      form={ask.expanded ? "page" : "drawer"}
      onExpand={ask.expand}
      onCollapse={ask.collapse}
      backLabel="Graph"
      onBack={() => {
        window.__QUESTIONS__!.closed = (window.__QUESTIONS__!.closed ?? 0) + 1;
        ask.back();
      }}
      onDismiss={ask.dismiss}
    >
      <Panel />
    </AskPage>
  );
}

createRoot(container).render(
  // Inside Ask & Chat's drawer or page, as `App.tsx` mounts it, so its Expand, Show as a drawer and Back are provable
  // here (rule 13). `position: relative`, as
  // App's main area is, so the page fills it.
  <div style={{ position: "relative", minHeight: "100vh" }}>
    <Page />
  </div>,
);
