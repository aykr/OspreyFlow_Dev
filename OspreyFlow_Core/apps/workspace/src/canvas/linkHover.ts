// What a link's hover tooltip says (ADR-115 E5, review item 11): its type, and how many links of that
// type join the same two entities in the canvas, in words — two lines, never joined with a dot.
import type Graph from "graphology";

import { linkTypeName, type NamedType } from "./linkLabel";

export function linkHoverText(graph: Graph, key: string, types: readonly NamedType[]): { type: string; count: string } | null {
  if (!graph.hasEdge(key)) return null;
  const data = graph.getEdgeAttribute(key, "data") as { type: string; source: string; target: string } | undefined;
  if (!data) return null;
  // The working set is a mixed multigraph (`workingset/store.ts`): `edges(a, b)` holds the links
  // between the two either way round.
  const same = graph
    .edges(data.source, data.target)
    .filter((k) => (graph.getEdgeAttribute(k, "data") as { type?: string } | undefined)?.type === data.type).length;
  return { type: linkTypeName(data.type, types), count: `${same} link${same === 1 ? "" : "s"} of this type between these two` };
}
