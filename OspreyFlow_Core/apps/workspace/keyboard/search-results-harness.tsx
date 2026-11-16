// Search results keyboard harness (the owner's navigation decision of 13 November 2026, Part A; ADR-145 Amendment 15
// Part A; `CLAUDE.md` rule 13): the real top bar's search box (`GlobalSearch`) and the real results page
// (`SearchResults`), with the App's own overlay hook (`search/useSearchResultsOverlay.ts`): Enter on the typed words
// opens the results over the view on screen, which stays beneath them out of reach (`inert`); Back returns to it with
// focus in the search box; a document read from them (a stand-in reader here) hides them until it closes. The
// Conduit is a stand-in kept here, so that the axe scan of every harness (`a11y/every-harness.spec.ts`) sees the page
// filled: `?state=none` answers nothing found, `?state=limited` the fallback, `?state=refused` a refusal; `?open=1`
// opens the results at load. What was shown, opened and asked is on `window.__SEARCH__`.
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

import "../src/design/tokens.css";
import "../src/design/primitives.css";
import type { Node } from "../../../packages/schemas/generated";
import type { OntologySchema } from "../../../packages/schemas/generated";
import { GlassCanvas } from "../src/canvas/GlassCanvas";
import { OntologyRegistry } from "../src/ontology/schema";
import { createWorkingSet } from "../src/workingset/store";
import { GlobalSearch } from "../src/search/GlobalSearch";
import { SearchResults } from "../src/search/SearchResults";
import { useSearchResultsOverlay } from "../src/search/useSearchResultsOverlay";
import { AskPage } from "../src/questions/AskPage";
import { useAskPage } from "../src/questions/useAskPage";
import { applyHarnessBrand } from "./brandHarness";

declare global {
  interface Window {
    __SEARCH__?: { sent: unknown[]; shown: string[][]; opened: string[]; asked: string[] };
  }
}

const params = new URLSearchParams(window.location.search);
const state = params.get("state");
window.__SEARCH__ = { sent: [], shown: [], opened: [], asked: [] };

const node = (id: string, type: string, properties: Record<string, unknown>): Node =>
  ({ id, type, properties, source_system_ids: [], provenance: { sources: [] }, classification: "OFFICIAL", handling: [] }) as unknown as Node;
const NODES = [
  node("p1", "Person", { family_name: "Kestrel", given_name: "Ann" }),
  node("o1", "Organisation", { name: "Kestrel Freight Ltd" }),
  node("d1", "Document", { title: "Invoice 44 from Kestrel Freight" }),
];
const PAGE = {
  query: "Kestrel", source: "index", limited: false, limited_reason: null, total: 57, counts_exact: true,
  groups: [
    { key: "Person", label: "People", count: 12 },
    { key: "Organisation", label: "Organisations", count: 2 },
    { key: "mentions", label: "Mentioned in documents", count: 43 },
  ],
  filters: { datasets: [{ id: "ds-1", name: "Fixture Corp", count: 40 }, { id: "ds-2", name: "Prison intel", count: 17 }], dates: { earliest: "2025-03-02", latest: "2026-10-30" } },
  page: 1, page_size: 20, more: true, nodes: NODES,
  results: [
    { node_ids: ["p1"], type: "Person", match: { band: "name_exact", why: "Family name is 'Kestrel'", field: "Family name" }, passage: [], date: null, datasets: ["ds-1"], is_document: false },
    { node_ids: ["o1"], type: "Organisation", match: { band: "name_words", why: "Name has the word 'Kestrel'", field: "Name" }, passage: [], date: null, datasets: ["ds-1"], is_document: false },
    { node_ids: ["d1"], type: "Document", match: { band: "mention_phrase", why: "Mentions 'Kestrel'", field: null },
      passage: [{ text: "…the carrier, ", match: false }, { text: "Kestrel", match: true }, { text: " Freight, invoiced the prison for…", match: false }],
      date: "2026-10-30", datasets: ["ds-2"], is_document: true },
  ],
}; // prettier-ignore

const realFetch = window.fetch.bind(window);
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input);
  if (url.endsWith("/suggest")) return new Response(JSON.stringify({ nodes: NODES.slice(0, 2), more: false }));
  if (!url.endsWith("/search")) return realFetch(input, init);
  const body = JSON.parse(String(init?.body)) as { query: string; page: number };
  window.__SEARCH__!.sent.push(body);
  // The real route's refusal of a query over MAX_QUERY_CHARS (200, counted by character), its body as FastAPI sends it.
  if ([...body.query].length > 200)
    return new Response(JSON.stringify({ detail: [{ type: "string_too_long", loc: ["body", "query"], msg: "String should have at most 200 characters",
      input: body.query, ctx: { max_length: 200 } }] }), { status: 422 }); // prettier-ignore
  if (state === "refused") return new Response(JSON.stringify({ detail: "Narrow the search: only the first 1,000 results can be paged." }), { status: 422 });
  if (state === "none") return new Response(JSON.stringify({ ...PAGE, query: body.query, total: 0, groups: [], results: [], nodes: [], more: false }));
  if (state === "limited")
    return new Response(JSON.stringify({ ...PAGE, query: body.query, source: "fallback", limited: true, counts_exact: false,
      limited_reason: "Results are limited: the search index cannot be reached.", filters: { datasets: PAGE.filters.datasets.map((d) => ({ ...d, count: null })), dates: null } })); // prettier-ignore
  return new Response(JSON.stringify({ ...PAGE, query: body.query, page: body.page, more: body.page < 2 }));
};

await applyHarnessBrand();

// `?canvas=1`: the real canvas, its toolbar and zoom column, under the results, in a view of its own as `App.tsx` lays the
// Graph out (`flex: 1; position: relative`, beside the results in the same main area): the live demo of 15 November 2026
// drew the canvas's toolbar and zoom over the results page, which a stand-in main area could never show.
const wantsCanvas = params.get("canvas") === "1";
// `?ask=1`: Ask & Chat's page (ADR-145 Amendment 18; Amendment 20's drawer expanded) open at load where `App.tsx` draws it, in the same main area and
// the same layer as the results, with App's own hook (`questions/useAskPage.ts`), so the stacking case can see the
// canvas's toolbar and zoom column drawn over it if they ever are.
const wantsAsk = params.get("ask") === "1";
const CANVAS_SCHEMA: OntologySchema = {
  version: 1,
  entity_types: [{ name: "Person", pole_class: "person", channel: "indigo", shape: "circle", icon: "person", identifiers: [] }],
  edge_types: [],
};
const workingSet = createWorkingSet();
if (wantsCanvas) workingSet.store.getState().applyDelta({ seq: 1, op: "add", nodes: [NODES[0]!], edges: [] });
const canvasOntology = new OntologyRegistry(CANVAS_SCHEMA);

function Harness() {
  // The App's own wiring (`search/useSearchResultsOverlay.ts`): when the results show, the view's reach, Back's focus,
  // and focus back into the results when a document read from them closes. The reader here is a stand-in.
  const [reading, setReading] = useState<string | null>(null);
  // As `App.tsx` hands them: a page opened while a document is read closes the reader and shows at once.
  const stopReading = () => setReading(null);
  const results = useSearchResultsOverlay(reading !== null, stopReading);
  const ask = useAskPage(reading !== null, results, wantsAsk ? "page" : null, stopReading);
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current || !params.get("open")) return;
    opened.current = true;
    results.open("Kestrel", "Graph");
  }, [results]);
  const searching = results.searching;
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--surface-app)", color: "var(--text-primary)" }}>
      <div className="top-bar" style={{ padding: "var(--sp-8)" }}>
        <GlobalSearch apiBaseUrl="http://keyboard-test.invalid" bearerToken="unused" investigationId="c1" onSelect={() => undefined} onSearch={(q) => results.open(q, "Graph")} />
        {/* A stand-in for the rail's Ask & Chat, which `App.tsx` gives `ask.toggle`. */}
        <button type="button" className="btn" aria-expanded={ask.shown} onClick={ask.toggle}>
          Ask & Chat
        </button>
      </div>
      <div style={{ flex: 1, position: "relative", display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div style={{ display: "contents" }} inert={results.viewInert || ask.viewInert ? true : undefined}>
          {wantsCanvas ? (
            <div style={{ flex: 1, position: "relative" }}>
              <GlassCanvas
                graph={workingSet.graph}
                store={workingSet.store}
                ontology={canvasOntology}
                edgeTypes={CANVAS_SCHEMA.edge_types}
                entityTypes={CANVAS_SCHEMA.entity_types}
                investigationId="c1"
                apiBaseUrl="http://keyboard-test.invalid"
                bearerToken="unused"
              />
            </div>
          ) : (
            <main style={{ padding: "var(--sp-16)" }}>
              <h1 style={{ margin: 0 }}>The graph</h1>
              <button type="button" className="btn">A control on the graph</button>
              {/* A document read from the view itself, not from either page (the reader here is a stand-in). */}
              <button type="button" className="btn" onClick={() => setReading("a document from the graph")}>
                Read a document from the graph
              </button>
            </main>
          )}
          {reading !== null && (
            <div role="dialog" aria-label={`Reading: ${reading}`} style={{ padding: "var(--sp-16)" }}>
              <button type="button" className="btn" onClick={() => setReading(null)}>
                Close
              </button>
            </div>
          )}
        </div>
        {ask.open && (
          <AskPage
            form={ask.expanded ? "page" : "drawer"}
            backLabel="Graph"
            onBack={ask.back} onDismiss={ask.dismiss}
            onExpand={ask.expand}
            onCollapse={ask.collapse}
            hidden={ask.pageHidden}
          >
            <p>Ask a question about this case.</p>
            {/* A document cited by an answer, read over the view, the page hidden meanwhile (the reader is a stand-in). */}
            <button type="button" className="btn" onClick={() => ask.readFromAnswer(() => setReading("a document from an answer"))}>
              Read a document from an answer
            </button>
          </AskPage>
        )}
        {searching !== null && (
          <SearchResults
            key={searching.at}
            hidden={results.resultsHidden}
            apiBaseUrl="http://keyboard-test.invalid"
            bearerToken="unused"
            investigationId="c1"
            query={searching.query}
            backLabel={searching.left}
            onBack={results.back}
            onShow={(nodes) => {
              window.__SEARCH__!.shown.push(nodes.map((n) => n.id));
              // As App's: the results and Ask & Chat's page left, its drawer kept (ADR-145 Amendment 20).
              ask.viewChosen();
            }}
            onOpenDocument={(id) => {
              window.__SEARCH__!.opened.push(id);
              setReading(id);
            }}
            onAsk={(words) => window.__SEARCH__!.asked.push(words)}
          />
        )}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
