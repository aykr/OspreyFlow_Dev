// Questions keyboard harness (ADR-098 decision 4): the case's questions to the model, mounted on
// its own as the Questions drawer renders it. `questions.spec.ts` intercepts the routes at the
// transport; what the panel hands back (a change to the view, a document to open) is exposed on
// `window.__QUESTIONS__`. A chosen `[G-n]` is proved against the real canvas in `harness.html?questions=1`.
import { useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import { Drawer } from "../src/design/primitives/Drawer";
import { QuestionsPanel } from "../src/questions/QuestionsPanel";
import { applyHarnessBrand } from "./brandHarness";

// The every-harness axe scan reads this call to scan GOV.UK too (`?brand=govuk`, ADR-132).
await applyHarnessBrand();

declare global {
  interface Window {
    __QUESTIONS__?: {
      deltas: unknown[];
      opened: string | null;
      closed?: number;
      /** What the last question asked about, as the panel sent it. */
      scope?: unknown;
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
    />
  );
}

createRoot(container).render(
  // Inside the Drawer, as `App.tsx` mounts it, so closing the drawer is provable here (rule 13).
  <Drawer open onClose={() => { window.__QUESTIONS__!.closed = (window.__QUESTIONS__!.closed ?? 0) + 1; }} title="Ask & Chat">
    <Panel />
  </Drawer>,
);
