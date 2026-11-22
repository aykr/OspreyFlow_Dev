// DESIGN.md v0.3 §5a: a node is drawn 14px across but has a 24×24 hit area (WCAG 2.2 SC 2.5.8). The
// renderer picks a node only where it is drawn, so a click it did not place on a node is checked here
// against each node's centre, in screen pixels.

/** Half of the 24px hit area. */
export const HIT_RADIUS = 12;

export interface ScreenNode {
  id: string;
  x: number;
  y: number;
  /** The radius the node is drawn at; a node drawn larger is reached across its own size. */
  size: number;
}

/** The nearest node whose reach covers `(x, y)`, or `null`. Between two at the same distance, the
 * later: it is drawn on top, and the renderer gives a click on the stack to it. */
export function nodeWithinReach(nodes: Iterable<ScreenNode>, x: number, y: number): string | null {
  let best: string | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const node of nodes) {
    const distance = Math.hypot(node.x - x, node.y - y);
    if (distance <= Math.max(HIT_RADIUS, node.size) && distance <= bestDistance) {
      best = node.id;
      bestDistance = distance;
    }
  }
  return best;
}
