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
import { GlobalSearch } from "../src/search/GlobalSearch";
import { SearchResults } from "../src/search/SearchResults";
import { useSearchResultsOverlay } from "../src/search/useSearchResultsOverlay";
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
  if (state === "refused") return new Response(JSON.stringify({ detail: "Narrow the search: only the first 1,000 results can be paged." }), { status: 422 });
  if (state === "none") return new Response(JSON.stringify({ ...PAGE, query: body.query, total: 0, groups: [], results: [], nodes: [], more: false }));
  if (state === "limited")
    return new Response(JSON.stringify({ ...PAGE, query: body.query, source: "fallback", limited: true, counts_exact: false,
      limited_reason: "Results are limited: the search index cannot be reached.", filters: { datasets: PAGE.filters.datasets.map((d) => ({ ...d, count: null })), dates: null } })); // prettier-ignore
  return new Response(JSON.stringify({ ...PAGE, query: body.query, page: body.page, more: body.page < 2 }));
};

await applyHarnessBrand();

function Harness() {
  // The App's own wiring (`search/useSearchResultsOverlay.ts`): when the results show, the view's reach, Back's focus,
  // and focus back into the results when a document read from them closes. The reader here is a stand-in.
  const [reading, setReading] = useState<string | null>(null);
  const results = useSearchResultsOverlay(reading !== null);
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
      </div>
      <div style={{ flex: 1, position: "relative", display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div style={{ display: "contents" }} inert={results.viewInert ? true : undefined}>
          <main style={{ padding: "var(--sp-16)" }}>
            <h1 style={{ margin: 0 }}>The graph</h1>
            <button type="button" className="btn">A control on the graph</button>
          </main>
          {reading !== null && (
            <div role="dialog" aria-label={`Reading: ${reading}`} style={{ padding: "var(--sp-16)" }}>
              <button type="button" className="btn" onClick={() => setReading(null)}>
                Close
              </button>
            </div>
          )}
        </div>
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
              results.leave();
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
