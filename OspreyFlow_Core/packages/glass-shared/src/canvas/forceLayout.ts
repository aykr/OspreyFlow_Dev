/**
 * A force-directed layout (Fruchterman–Reingold): every pair of nodes repels, every edge pulls its
 * two ends together, and a small pull towards the centre keeps separate groups from drifting
 * apart. Kept apart from the canvas so it is a pure function of its input, repeatable and testable
 * without a browser.
 *
 * **Deliberately bounded.** Every pair is compared, so the cost grows with the square of the
 * node count. Up to `FORCE_LAYOUT_MAX_NODES` that is a fraction of a second; beyond it the
 * function returns `null` and the caller keeps the positions it has, because freezing the page
 * would be worse than an unsettled picture. The spec's own answer for the large case (ForceAtlas2
 * in a worker, 02_GLASS_FRONTEND.md §5) is not built and has not been measured here.
 */

export interface LayoutNode {
  id: string;
  x: number;
  y: number;
  /** A pinned node keeps its position; the others settle around it. */
  pinned?: boolean;
}

export type LayoutEdge = [source: string, target: string];

/** World units between two linked nodes at rest. */
export const IDEAL_EDGE_LENGTH = 80;
export const FORCE_LAYOUT_MAX_NODES = 1000;

/** Pair comparisons the layout may spend: more nodes, fewer passes. Measured, see the build plan. */
const PAIR_BUDGET = 25_000_000;
const MAX_ITERATIONS = 200;
const MIN_ITERATIONS = 60;
const CENTRE_PULL = 0.03;

/**
 * Settled positions, by node id; `null` when the graph is too big to settle quickly. The input
 * positions are the starting point, so a graph that is already laid out changes only a little
 * when a node is added.
 */
export function settleLayout(
  nodes: readonly LayoutNode[],
  edges: readonly LayoutEdge[],
): Map<string, { x: number; y: number }> | null {
  const n = nodes.length;
  if (n > FORCE_LAYOUT_MAX_NODES) return null;

  const index = new Map(nodes.map((node, i) => [node.id, i]));
  const xs = Float64Array.from(
    nodes,
    (node, i) => node.x + (isCoincident(nodes, i) ? jitter(i) : 0),
  );
  const ys = Float64Array.from(
    nodes,
    (node, i) => node.y + (isCoincident(nodes, i) ? jitter(i + 7) : 0),
  );
  const links: [number, number][] = [];
  for (const [a, b] of edges) {
    const i = index.get(a);
    const j = index.get(b);
    if (i !== undefined && j !== undefined && i !== j) links.push([i, j]);
  }

  const k = IDEAL_EDGE_LENGTH;
  const kk = k * k;
  const dx = new Float64Array(n);
  const dy = new Float64Array(n);
  const pairs = Math.max(1, (n * (n - 1)) / 2);
  const iterations = Math.max(
    MIN_ITERATIONS,
    Math.min(MAX_ITERATIONS, Math.floor(PAIR_BUDGET / pairs)),
  );
  for (let step = 0; step < iterations; step++) {
    const temperature = k * 2 * (1 - step / iterations);
    dx.fill(0);
    dy.fill(0);
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let vx = xs[i]! - xs[j]!;
        let vy = ys[i]! - ys[j]!;
        let d = Math.sqrt(vx * vx + vy * vy);
        if (d < 0.01) {
          vx = jitter(i + j);
          vy = jitter(i * 3 + j);
          d = Math.sqrt(vx * vx + vy * vy);
        }
        const push = kk / (d * d);
        dx[i]! += vx * push;
        dy[i]! += vy * push;
        dx[j]! -= vx * push;
        dy[j]! -= vy * push;
      }
    }
    for (const [i, j] of links) {
      const vx = xs[i]! - xs[j]!;
      const vy = ys[i]! - ys[j]!;
      const d = Math.max(Math.sqrt(vx * vx + vy * vy), 0.01);
      const pull = d / k;
      dx[i]! -= vx * pull;
      dy[i]! -= vy * pull;
      dx[j]! += vx * pull;
      dy[j]! += vy * pull;
    }
    for (let i = 0; i < n; i++) {
      if (nodes[i]!.pinned) continue;
      dx[i]! -= xs[i]! * CENTRE_PULL;
      dy[i]! -= ys[i]! * CENTRE_PULL;
      const length = Math.sqrt(dx[i]! * dx[i]! + dy[i]! * dy[i]!);
      if (length === 0) continue;
      const move = Math.min(length, temperature);
      xs[i]! += (dx[i]! / length) * move;
      ys[i]! += (dy[i]! / length) * move;
    }
  }

  return new Map(
    nodes.map((node, i) => [
      node.id,
      node.pinned ? { x: node.x, y: node.y } : { x: xs[i]!, y: ys[i]! },
    ]),
  );
}

function isCoincident(nodes: readonly LayoutNode[], i: number): boolean {
  const a = nodes[i]!;
  for (let j = 0; j < i; j++)
    if (nodes[j]!.x === a.x && nodes[j]!.y === a.y) return true;
  return false;
}

/** A small repeatable nudge, so nodes starting on one spot do not stay on it. */
function jitter(seed: number): number {
  return ((Math.sin(seed * 12.9898) * 43758.5453) % 1) * 4;
}
