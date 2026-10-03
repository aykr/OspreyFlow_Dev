import { useEffect, useRef, useState } from "react";

import type { Node } from "../../../../packages/schemas/generated";
import { Combobox } from "../design/primitives/Combobox";
import { SearchFilters } from "./SearchFilters";
import {
  DEFAULT_SEARCH_OPTIONS,
  displayValue,
  activeFilterCount,
  matchOnScreen,
  suggestBody,
  type SearchOptions,
} from "./searchOptions";

export interface GlobalSearchProps {
  apiBaseUrl: string;
  bearerToken: string;
  onSelect: (node: Node) => void;
  /** The entity types the Filters panel offers (from the ontology). Empty hides that choice. */
  entityTypes?: readonly string[];
  /** The nodes drawn on the canvas now, for "Only nodes on screen". Called per search, not stored. */
  screenNodes?: () => readonly Node[];
}

/** A prefix shorter than this is not worth asking about; the Conduit refuses it too (ADR-059). */
export const SUGGEST_MIN_CHARS = 3;
/** The pause after the last keystroke before the Conduit is asked. */
export const SUGGEST_PAUSE_MS = 250;
const SUGGEST_LIMIT = 10;
/** How long the "more match" hint stays in view before it fades. It is not a state to act on, only
 * a nudge, so it should not sit over the page for as long as the list is open. */
export const SEARCH_HINT_MS = 4000;

type Outcome = "idle" | "found" | "none" | "unavailable";

/** `spec/02_GLASS_FRONTEND.md`'s workspace layout: "⌘K — Search entities,
 * identifiers, documents". ADR-059: from the third character, after a pause, the box asks
 * `POST /v1/suggest` for nodes whose identifiers *start with* what is typed (`/v1/search` stays an
 * exact match). An answer to a question the analyst has already moved past is dropped, a list cut
 * off at ten says so, and an unanswered question says so instead of leaving the last list standing. */
export function GlobalSearch({ apiBaseUrl, bearerToken, onSelect, entityTypes = [], screenNodes }: GlobalSearchProps) {
  const [results, setResults] = useState<Node[]>([]);
  const [query, setQuery] = useState("");
  const [more, setMore] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latest = useRef(0);
  const [options, setOptions] = useState<SearchOptions>(DEFAULT_SEARCH_OPTIONS);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filterCount = activeFilterCount(options);
  const onScreen = options.onScreenOnly;

  useEffect(() => () => clearTimeout(timer.current), []);

  function settle(next: Outcome, nodes: Node[], hasMore: boolean): void {
    setOutcome(next);
    setResults(nodes);
    setMore(hasMore);
  }

  async function ask(value: string, mine: number, using: SearchOptions): Promise<void> {
    try {
      const response = await fetch(`${apiBaseUrl}/v1/suggest`, {
        method: "POST",
        headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
        body: JSON.stringify(suggestBody(value, SUGGEST_LIMIT, using)),
      });
      if (mine !== latest.current) return;
      if (!response.ok) {
        settle("unavailable", [], false);
        return;
      }
      const body = (await response.json()) as { nodes: Node[]; more: boolean };
      if (mine !== latest.current) return;
      settle(body.nodes.length > 0 ? "found" : "none", body.nodes, body.more);
    } catch {
      if (mine === latest.current) settle("unavailable", [], false);
    }
  }

  function search(value: string, using: SearchOptions): void {
    clearTimeout(timer.current);
    latest.current += 1;
    const mine = latest.current;
    if (using.onScreenOnly) {
      // Nothing is asked of the Conduit: the nodes are already here, so one character is enough
      // and there is no need to wait for a pause.
      const found = matchOnScreen(screenNodes?.() ?? [], value, using, SUGGEST_LIMIT);
      settle(value === "" ? "idle" : found.nodes.length > 0 ? "found" : "none", found.nodes, found.more);
      return;
    }
    if (value.length < SUGGEST_MIN_CHARS) {
      settle("idle", [], false);
      return;
    }
    timer.current = setTimeout(() => void ask(value, mine, using), SUGGEST_PAUSE_MS);
  }

  function onQueryChange(value: string): void {
    setQuery(value);
    search(value, options);
  }

  const firstRender = useRef(true);
  useEffect(() => {
    // A changed filter asks the question again; the first render has nothing to ask.
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    search(query, options);
    // `query` is deliberately not a dependency: typing already searches, in `onQueryChange`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options]);

  const status =
    outcome === "unavailable"
      ? "Suggestions are unavailable."
      : outcome === "none"
        ? onScreen
          ? "No node on screen matches that."
          : "No match starts with that."
        : more
          ? `Showing the first ${results.length}; more match. Keep typing to narrow.`
          : null;

  // Only the nudge fades. "Nothing matches" and "could not answer" are answers to what was typed and
  // stay while it stands. A new answer (a new `results`) brings the nudge back.
  const nudge = status !== null && outcome !== "none" && outcome !== "unavailable";
  const [faded, setFaded] = useState(false);
  useEffect(() => {
    setFaded(false);
    if (!nudge) return;
    const timeout = setTimeout(() => setFaded(true), SEARCH_HINT_MS);
    return () => clearTimeout(timeout);
  }, [nudge, status, results]);

  return (
    <div className="global-search">
      <div className="global-search__field">
        <Combobox
          aria-label="Search entities, identifiers, documents"
          placeholder="Search entities, identifiers, documents"
          value={query}
          options={results.map((node) => ({ value: node.id, label: `${node.type}: ${displayValue(node)}` }))}
          onQueryChange={onQueryChange}
          onChange={(value) => {
            const node = results.find((n) => n.id === value);
            if (node) onSelect(node);
          }}
        />
        <button
          type="button"
          className="global-search__filters"
          aria-expanded={filtersOpen}
          aria-label={filterCount > 0 ? `Filters (${filterCount})` : "Filters"}
          title="Filters"
          data-active={filterCount > 0 ? "true" : undefined}
          onClick={() => setFiltersOpen((open) => !open)}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <path d="M2 3h12l-4.5 5.5V13l-3-1.5V8.5z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          </svg>
          {filterCount > 0 && <span className="global-search__count">{filterCount}</span>}
        </button>
      </div>
      {filtersOpen && <SearchFilters options={options} entityTypes={entityTypes} onChange={setOptions} />}
      {status && (
        <div role="status" className="global-search__status" data-faded={nudge && faded ? "true" : undefined}>
          {status}
        </div>
      )}
    </div>
  );
}
