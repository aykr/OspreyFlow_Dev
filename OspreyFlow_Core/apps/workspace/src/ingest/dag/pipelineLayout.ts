// Where each pipeline node sits on the canvas (ADR-108 phase A): columns by longest path from a
// root (a stage draws right of everything that feeds it), rows in the node list's own stable
// order. Pure, so the layout is a unit-tested fact rather than a renderer's accident.
import type { PipelineGraph } from "../../../../../packages/schemas/generated";

export interface PlacedNode {
  id: string;
  column: number;
  row: number;
}

export function pipelineLayout(graph: PipelineGraph): PlacedNode[] {
  // The generated types leave the lists optional (they default server-side); absent means empty.
  const allNodes = graph.nodes ?? [];
  const allEdges = graph.edges ?? [];
  const feeders = new Map<string, string[]>();
  for (const edge of allEdges) {
    const into = feeders.get(edge.target) ?? [];
    into.push(edge.source);
    feeders.set(edge.target, into);
  }
  const depth = new Map<string, number>();
  const visiting = new Set<string>();
  function depthOf(id: string): number {
    const known = depth.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) return 0; // a cycle never reaches the canvas (validation), but never hang
    visiting.add(id);
    const above = (feeders.get(id) ?? []).map(depthOf);
    const found = above.length === 0 ? 0 : Math.max(...above) + 1;
    visiting.delete(id);
    depth.set(id, found);
    return found;
  }
  const rows = new Map<number, number>();
  return allNodes.map((node) => {
    const column = depthOf(node.id);
    const row = rows.get(column) ?? 0;
    rows.set(column, row + 1);
    return { id: node.id, column, row };
  });
}
