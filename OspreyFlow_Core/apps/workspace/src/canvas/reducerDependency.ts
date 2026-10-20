// What the canvas's reducers depend on, told to Sigma 4 (ADR-118).
//
// Sigma 4 re-evaluates every node's and every link's style whenever its graph-wide state changes,
// if the styles might read that state, and it assumes any reducer does. Its graph-wide state
// changes when a zoom starts and when it stops, when a pan starts and stops, and when the pointer
// comes onto or leaves a node. So on the 50k/250k fixture every one of those ran both reducers over
// 300,000 items: 1.65 s on a real GPU, and a pan/zoom sweep managed two frames in four seconds
// where Sigma 3 drew 150 (measured 20 October 2026).
//
// The canvas's reducers never read that state. They read a node's own state (`isHovered`) and the
// canvas's own (selection, hover, folds, hidden links), and every change to the canvas's own state
// is followed by a refresh the canvas asks for. "Item state" is what Sigma calls that: an item is
// re-evaluated when its own state changes. Sigma 4 has no setting for it, so the analysis it keeps
// is corrected in place, and the canvas refuses to start if the analysis is not where it was: a
// later Sigma that moved it would otherwise bring the stalls back without a word.

interface StyleAnalysis {
  dependency: string;
}

/** The part of Sigma this needs; a test passes a fake. */
export interface AnalysedRenderer {
  internals?: { nodeStyleAnalysis?: StyleAnalysis };
  edgeStyleAnalysis?: StyleAnalysis;
}

/** Tells `sigma` its reducers read each item's own state, not the graph-wide state. Throws if
 * Sigma's analysis is not where Sigma 4.0 keeps it, or is not the reducers' "graph-state". */
export function declareReducersReadItemStateOnly(sigma: unknown): void {
  const held = sigma as AnalysedRenderer;
  const node = held.internals?.nodeStyleAnalysis;
  const edge = held.edgeStyleAnalysis;
  if (!node || !edge || node.dependency !== "graph-state" || edge.dependency !== "graph-state") {
    throw new Error(
      "The graph renderer's style analysis is not where Sigma 4.0 keeps it: see canvas/reducerDependency.ts before upgrading Sigma.",
    );
  }
  node.dependency = "item-state";
  edge.dependency = "item-state";
}
