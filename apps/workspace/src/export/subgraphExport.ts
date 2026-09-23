// Subgraph export — Phase 8 Stage 4h, `02_GLASS_FRONTEND.md` §10.1 ("Subgraph — JSON, the working
// set's own `Node`/`Edge` wire shape... a subgraph export is a snapshot in the same shape the
// Glass already receives over the wire") and §10.3 (the mark "as a top-level structured field
// with no visual rendering").
import type Graph from "graphology";

import type { ExportManifest, ExportMark } from "./api";

export interface SubgraphArtefact {
  mark: ExportMark;
  manifest: ExportManifest;
  nodes: Array<{ id: string; [key: string]: unknown }>;
  edges: Array<{ id: string; [key: string]: unknown }>;
}

/** Pure: the working set's own `data` attribute on every node/edge is already the real
 * `Node`/`Edge` wire shape (the same attribute `ExportPanel.tsx`'s own `selectionItems` already
 * reads for the handling-gate selection) — this function only wraps that snapshot with the mark
 * and manifest, it does not re-derive or reshape the graph content itself. */
export function buildSubgraphArtefact(
  graph: Graph,
  mark: ExportMark,
  manifest: ExportManifest,
): SubgraphArtefact {
  const nodes: Array<{ id: string; [key: string]: unknown }> = [];
  graph.forEachNode((id) => {
    const data = graph.getNodeAttribute(id, "data") as Record<string, unknown> | undefined;
    nodes.push({ id, ...(data ?? {}) });
  });
  const edges: Array<{ id: string; [key: string]: unknown }> = [];
  graph.forEachEdge((id) => {
    const data = graph.getEdgeAttribute(id, "data") as Record<string, unknown> | undefined;
    edges.push({ id, ...(data ?? {}) });
  });
  return { mark, manifest, nodes, edges };
}

/** The downloadable form — a single JSON string, the artefact itself, not only the in-memory
 * shape. Stable key order (`mark`, `manifest`, `nodes`, `edges`) so two exports of the same
 * selection diff cleanly. */
export function serialiseSubgraphArtefact(artefact: SubgraphArtefact): string {
  return JSON.stringify(artefact, null, 2);
}
