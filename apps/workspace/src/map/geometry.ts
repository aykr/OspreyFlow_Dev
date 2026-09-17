// A shared, coordinate-system-agnostic point-in-polygon test —
// `07_BUILD_PLAN.md` Phase 5 Checkpoint 3c. Standard even-odd ray
// casting; consolidated here rather than left duplicated because the
// exact same algorithm already existed in `canvas/GlassCanvas.tsx` for
// screen-space lasso selection (`{x, y}` viewport pixels) — the boundary
// spatial filter below needs the identical test against `{x, y}` lon/lat
// pairs instead, and ray casting has no notion of units or projection, so
// one function correctly serves both callers.
export interface Point2D {
  x: number;
  y: number;
}

export function pointInPolygon(point: Point2D, polygon: readonly Point2D[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const pi = polygon[i]!;
    const pj = polygon[j]!;
    const intersects =
      pi.y > point.y !== pj.y > point.y &&
      point.x < ((pj.x - pi.x) * (point.y - pi.y)) / (pj.y - pi.y) + pi.x;
    if (intersects) inside = !inside;
  }
  return inside;
}
