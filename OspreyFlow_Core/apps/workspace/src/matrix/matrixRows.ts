// The Matrix view's rows — `02_GLASS_FRONTEND.md` §6 ("the Matrix view is not a novelty, it is the
// screen-reader-navigable rendering of the same data") and §2 rule 1 ("Graph, Map and Matrix are
// three renderings of the same graphology instance").
//
// Read from the working set's own graph and nothing else: no request, no count from the server.
// What the reader may not see never reaches that graph (rule 3, in the adapter), so it cannot reach
// a row either, and the Glass learns no number about it (rule 7). A node the cross-filter dims stays
// a row, marked as dimmed, as it stays on the canvas (§2 rule 2).
import type { ProvenanceState } from "../../../../packages/schemas/generated/Node";
import { nodeLabel } from "../canvas/nodeAttributes";
import { linkTypeName, type NamedType } from "../canvas/linkLabel";
import type { WorkingSetGraph } from "../workingset/store";

/** How many rows a page of the Matrix shows. A longer view is paged, and says which rows are shown
 * (rule 2: never a silent cut). Small enough that a page draws well inside §5's budget at 50k. */
export const PAGE_SIZE = 100;

export interface EntityRow {
  id: string;
  /** The name the canvas draws for it (the analyst's chosen label, else the default). */
  name: string;
  type: string;
  /** The node's own protective marking, as the Inspector's badge shows it. */
  marking: string | null;
  provenance: ProvenanceState;
  /** Its links in this view — what the working set holds, never the store's count. */
  links: number;
  /** The cross-filter dims it on the canvas. */
  dimmed: boolean;
}

export interface LinkRow {
  id: string;
  /** The link type's label, as the canvas and the Inspector read it (ADR-091). */
  type: string;
  from: string;
  fromId: string;
  to: string;
  toId: string;
  marking: string | null;
  provenance: ProvenanceState;
  dimmed: boolean;
  /** ADR-139: its connection strength as the reader may see it, once worked out; else `null`. */
  strength: number | null;
  /** ADR-139: the shared-attribute rarity of its two ends, once worked out; else `null`. */
  rarity: number | null;
}

/** ADR-139's two values for the link table, by link id. */
export interface LinkValues {
  strength?: Readonly<Record<string, number>>;
  rarity?: Readonly<Record<string, number>>;
}

const NONE: ReadonlySet<string> = new Set();

export function entityRows(graph: WorkingSetGraph, dimmed: ReadonlySet<string> = NONE): EntityRow[] {
  return graph.mapNodes((id, attributes) => {
    const node = attributes.data;
    return {
      id,
      name: nodeLabel(node),
      type: node.type,
      marking: node.handling?.classification ?? null,
      provenance: node.provenance.state,
      links: graph.edges(id).length,
      dimmed: dimmed.has(id),
    };
  });
}

export function linkRows(
  graph: WorkingSetGraph,
  edgeTypes: readonly NamedType[],
  dimmed: ReadonlySet<string> = NONE,
  values: LinkValues = {},
): LinkRow[] {
  // Each end's name is worked out once, not once per link (a busy node has thousands).
  const names = new Map<string, string>();
  const nameOf = (id: string): string => {
    let name = names.get(id);
    if (name === undefined) {
      name = nodeLabel(graph.getNodeAttribute(id, "data"));
      names.set(id, name);
    }
    return name;
  };
  return graph.mapEdges((id, attributes, source, target) => {
    const edge = attributes.data;
    return {
      id,
      type: linkTypeName(edge.type, edgeTypes),
      from: nameOf(source),
      fromId: source,
      to: nameOf(target),
      toId: target,
      marking: edge.handling?.classification ?? null,
      provenance: edge.provenance.state,
      dimmed: dimmed.has(id),
      strength: values.strength?.[id] ?? null,
      rarity: values.rarity?.[id] ?? null,
    };
  });
}

/** Provenance in words (rule 5: what a model proposed is labelled inferred until a person confirms
 * it). The canvas carries it by stroke; a table carries it by text. */
export function provenanceText(state: ProvenanceState): string {
  switch (state) {
    case "inferred":
      return "Inferred";
    case "unresolved":
      return "Unresolved";
    default:
      return "Asserted";
  }
}

export type SortDirection = "ascending" | "descending";

const COLLATOR = new Intl.Collator("en-GB", { numeric: true, sensitivity: "base" });

function compareValues(a: unknown, b: unknown): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  // A value not worked out (ADR-139's strength or rarity, `null`) compares as "", below every
  // number written out, so it sorts below every value worked out.
  if (typeof a === "boolean" && typeof b === "boolean") return Number(a) - Number(b);
  return COLLATOR.compare(a == null ? "" : String(a), b == null ? "" : String(b));
}

/** Sorted by `key`, either way. Ties fall back to the name (or the From end), then the id, so a
 * re-sort never shuffles rows that compare equal. */
export function sortRows<R extends { id: string }>(
  rows: readonly R[],
  key: keyof R & string,
  direction: SortDirection,
): R[] {
  const sign = direction === "ascending" ? 1 : -1;
  const tie = (row: R): unknown => (row as { name?: unknown; from?: unknown }).name ?? (row as { from?: unknown }).from;
  return [...rows].sort(
    (a, b) =>
      sign * compareValues(a[key], b[key]) ||
      compareValues(tie(a), tie(b)) ||
      COLLATOR.compare(a.id, b.id),
  );
}

export interface Page<R> {
  rows: R[];
  /** Zero-based. */
  page: number;
  pages: number;
  /** One-based positions of the first and last row shown; both 0 when there are none. */
  first: number;
  last: number;
  total: number;
}

export function pageOf<R>(rows: readonly R[], page: number, size: number = PAGE_SIZE): Page<R> {
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / size));
  const at = Math.min(Math.max(0, page), pages - 1);
  const start = at * size;
  const shown = rows.slice(start, start + size);
  return {
    rows: shown,
    page: at,
    pages,
    first: total === 0 ? 0 : start + 1,
    last: start + shown.length,
    total,
  };
}

/** The page `id` is on, or `null` when no row has it. */
export function pageContaining<R extends { id: string }>(
  rows: readonly R[],
  id: string,
  size: number = PAGE_SIZE,
): number | null {
  const index = rows.findIndex((row) => row.id === id);
  return index < 0 ? null : Math.floor(index / size);
}
