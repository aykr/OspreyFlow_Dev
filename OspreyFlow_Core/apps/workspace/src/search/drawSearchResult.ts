import type { Node } from "../../../../packages/schemas/generated";

/** Choosing a search result draws the node and everything within this many links of it (ADR-070).
 * The server counts it first and the canvas asks before drawing a very large result, so nothing is
 * cut silently and nothing very large arrives unannounced. */
export const SEARCH_DRAW_DEPTH = 3;

/** Puts the chosen node in the case's working set (`seed`: through `/seed`, as Explore's adds go),
 * then asks the canvas to draw outwards from it. Never a local add alone: a node only on screen is
 * not in the working set, so a cancelled draw left one that "Show links among these" could not see
 * (build order step 18c, D5). */
export async function drawSearchResult(
  seed: (nodes: readonly Node[]) => Promise<boolean>,
  node: Node,
  canvas: { expandFrom: (nodeId: string, depth: number) => void } | null,
): Promise<void> {
  if (!(await seed([node]))) return;
  canvas?.expandFrom(node.id, SEARCH_DRAW_DEPTH);
}
