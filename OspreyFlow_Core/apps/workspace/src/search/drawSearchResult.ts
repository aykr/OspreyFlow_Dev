import type { Node } from "../../../../packages/schemas/generated";
import type { WorkingSet } from "../workingset/store";

/** Choosing a search result draws the node and everything within this many links of it (ADR-070).
 * The server counts it first and the canvas asks before drawing a very large result, so nothing is
 * cut silently and nothing very large arrives unannounced. */
export const SEARCH_DRAW_DEPTH = 3;

/** Puts the chosen node on the canvas, then asks the canvas to draw outwards from it. */
export function drawSearchResult(
  store: WorkingSet["store"],
  node: Node,
  canvas: { expandFrom: (nodeId: string, depth: number) => void } | null,
): void {
  store.getState().applyDelta({ seq: store.getState().seq, op: "add", nodes: [node], edges: [] });
  canvas?.expandFrom(node.id, SEARCH_DRAW_DEPTH);
}
