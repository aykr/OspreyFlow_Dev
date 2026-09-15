import { useState } from "react";

import type { Node } from "../../../../packages/schemas/generated";
import { Combobox } from "../design/primitives/Combobox";

export interface GlobalSearchProps {
  apiBaseUrl: string;
  bearerToken: string;
  onSelect: (node: Node) => void;
}

/** `docs/02_GLASS_FRONTEND.md`'s workspace layout: "⌘K — Search entities,
 * identifiers, documents". `services/api/search.py`'s v1 scope note
 * applies here too: exact identifier match against the graph, not full
 * text — the search box finds and centres an entity already in the
 * graph, it does not (yet) search document content. */
export function GlobalSearch({ apiBaseUrl, bearerToken, onSelect }: GlobalSearchProps) {
  const [results, setResults] = useState<Node[]>([]);
  const [query, setQuery] = useState("");

  async function runSearch(value: string): Promise<void> {
    setQuery(value);
    if (!value) {
      setResults([]);
      return;
    }
    const response = await fetch(`${apiBaseUrl}/v1/search`, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query: value }),
    });
    if (!response.ok) return;
    const body = (await response.json()) as { nodes: Node[] };
    setResults(body.nodes);
  }

  return (
    <Combobox
      aria-label="Search entities, identifiers, documents"
      placeholder="Search entities, identifiers, documents"
      value={query}
      options={results.map((node) => ({ value: node.id, label: `${node.type}: ${node.id}` }))}
      onQueryChange={(value) => void runSearch(value)}
      onChange={(value) => {
        const node = results.find((n) => n.id === value);
        if (node) onSelect(node);
      }}
    />
  );
}
