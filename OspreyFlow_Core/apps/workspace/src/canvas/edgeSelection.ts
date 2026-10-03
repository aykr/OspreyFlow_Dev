/** How far from the drawn line, in screen pixels, a click still counts as on the link. The WebGL
 * picking Sigma does follows the drawn width, which for a one- or two-pixel line is too fine to
 * hit reliably. */
export const EDGE_HIT_PX = 6;

export interface ScreenSegment {
  id: string;
  ax: number;
  ay: number;
  bx: number;
  by: number;
}

function distanceToSegment(x: number, y: number, s: ScreenSegment): number {
  const dx = s.bx - s.ax;
  const dy = s.by - s.ay;
  const lengthSquared = dx * dx + dy * dy;
  if (lengthSquared === 0) return Math.hypot(x - s.ax, y - s.ay);
  const along = Math.max(0, Math.min(1, ((x - s.ax) * dx + (y - s.ay) * dy) / lengthSquared));
  return Math.hypot(x - (s.ax + along * dx), y - (s.ay + along * dy));
}

/** The link nearest the point within `reach` pixels, or `null`. A pure function of screen
 * coordinates, so the click target can be wider than the line without touching the renderer. */
export function nearestEdge(
  x: number,
  y: number,
  segments: readonly ScreenSegment[],
  reach: number = EDGE_HIT_PX,
): string | null {
  let best: string | null = null;
  let bestDistance = Infinity;
  for (const segment of segments) {
    const distance = distanceToSegment(x, y, segment);
    if (distance <= reach && distance < bestDistance) {
      best = segment.id;
      bestDistance = distance;
    }
  }
  return best;
}

/** The next (or previous) link of a node, for stepping through them by keyboard. Sorted by id so
 * the order is the same every time; wraps round; starts again if the selected link is not one of
 * this node's. */
export function nextLink(edgeIds: readonly string[], current: string | null, step: 1 | -1): string | null {
  if (edgeIds.length === 0) return null;
  const sorted = [...edgeIds].sort();
  const at = current === null ? -1 : sorted.indexOf(current);
  if (at === -1) return step === 1 ? sorted[0]! : sorted[sorted.length - 1]!;
  return sorted[(at + step + sorted.length) % sorted.length]!;
}
