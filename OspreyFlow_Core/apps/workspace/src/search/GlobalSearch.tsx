import { useEffect, useRef, useState } from "react";

import type { Node } from "../../../../packages/schemas/generated";
import { Combobox } from "../design/primitives/Combobox";

export interface GlobalSearchProps {
  apiBaseUrl: string;
  bearerToken: string;
  onSelect: (node: Node) => void;
}

/** A prefix shorter than this is not worth asking about; the Conduit refuses it too (ADR-059). */
export const SUGGEST_MIN_CHARS = 3;
/** The pause after the last keystroke before the Conduit is asked. */
export const SUGGEST_PAUSE_MS = 250;
const SUGGEST_LIMIT = 10;

/** The properties that hold the value an analyst types, in the order worth showing. A suggestion
 * labelled with the node's opaque id tells the analyst nothing about which account it is. */
const DISPLAY_PROPERTIES = ["value_normalised", "name", "email", "handle", "nino", "imei", "postcode", "org_ref"];

function displayValue(node: Node): string {
  const properties = (node.properties ?? {}) as Record<string, unknown>;
  for (const key of DISPLAY_PROPERTIES) {
    const value = properties[key];
    if (typeof value === "string" && value) return value;
  }
  return node.id;
}

type Outcome = "idle" | "found" | "none" | "unavailable";

/** `spec/02_GLASS_FRONTEND.md`'s workspace layout: "⌘K — Search entities,
 * identifiers, documents". ADR-059: from the third character, after a pause, the box asks
 * `POST /v1/suggest` for nodes whose identifiers *start with* what is typed (`/v1/search` stays an
 * exact match). An answer to a question the analyst has already moved past is dropped, a list cut
 * off at ten says so, and an unanswered question says so instead of leaving the last list standing. */
export function GlobalSearch({ apiBaseUrl, bearerToken, onSelect }: GlobalSearchProps) {
  const [results, setResults] = useState<Node[]>([]);
  const [query, setQuery] = useState("");
  const [more, setMore] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latest = useRef(0);

  useEffect(() => () => clearTimeout(timer.current), []);

  function settle(next: Outcome, nodes: Node[], hasMore: boolean): void {
    setOutcome(next);
    setResults(nodes);
    setMore(hasMore);
  }

  async function ask(value: string, mine: number): Promise<void> {
    try {
      const response = await fetch(`${apiBaseUrl}/v1/suggest`, {
        method: "POST",
        headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ query: value, limit: SUGGEST_LIMIT }),
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

  function onQueryChange(value: string): void {
    setQuery(value);
    clearTimeout(timer.current);
    latest.current += 1;
    const mine = latest.current;
    if (value.length < SUGGEST_MIN_CHARS) {
      settle("idle", [], false);
      return;
    }
    timer.current = setTimeout(() => void ask(value, mine), SUGGEST_PAUSE_MS);
  }

  const status =
    outcome === "unavailable"
      ? "Suggestions are unavailable."
      : outcome === "none"
        ? "No match starts with that."
        : more
          ? `Showing the first ${results.length}; more match. Keep typing to narrow.`
          : null;

  return (
    <div className="global-search">
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
      {status && <div role="status" className="global-search__status">{status}</div>}
    </div>
  );
}
