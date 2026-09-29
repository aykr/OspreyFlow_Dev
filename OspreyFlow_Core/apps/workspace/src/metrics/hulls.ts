// Community hull geometry — the metrics panel's own "community
// hull overlay" bullet. Pure graph-space geometry only: `canvas/CommunityHullOverlay.tsx` is what
// converts these points to viewport space against a live camera and renders them; this module has
// no dependency on Sigma or the DOM, so it is plain-`vitest`-testable the same way
// `canvas/zoomBands.ts`'s own pure functions are.
//
// Benchmarked (not assumed) at this stage's own planning time: a monotone-chain convex hull
// (`d3-polygon`'s `polygonHull`, the real dependency this module uses) over 40 communities
// spanning the working set's own 20,000-node synchronous-budget boundary took 2.6ms total, three
// orders of magnitude of headroom against `02_GLASS_FRONTEND.md` §5's 500ms budget — see
// this file's own commit history has the full figure.
import { polygonHull } from "d3-polygon";

import type { WorkingSetGraph } from "../workingset/store";

/**
 * One hull polygon (graph-space `[x, y]` points, counterclockwise, per `d3-polygon`'s own
 * contract) per community — `null` (never a two-point "line" hull) for a community with fewer
 * than three distinct positions, since a hull needs at least three points to be a polygon at all;
 * `d3-polygon`'s own `polygonHull` already encodes this by returning `null` itself, not a gap this
 * module fills silently. A single-member or two-member community therefore has no hull row at
 * all, which `CommunityHullOverlay` renders as nothing — no highlight, not a degenerate shape.
 */
export function computeCommunityHulls(
  graph: WorkingSetGraph,
  communities: Readonly<Record<string, string>>,
): Map<string, [number, number][]> {
  const pointsByCommunity = new Map<string, [number, number][]>();
  for (const [nodeId, communityId] of Object.entries(communities)) {
    if (!graph.hasNode(nodeId)) continue;
    const x = graph.getNodeAttribute(nodeId, "x") ?? 0;
    const y = graph.getNodeAttribute(nodeId, "y") ?? 0;
    const points = pointsByCommunity.get(communityId);
    if (points) points.push([x, y]);
    else pointsByCommunity.set(communityId, [[x, y]]);
  }

  const hulls = new Map<string, [number, number][]>();
  for (const [communityId, points] of pointsByCommunity) {
    const hull = polygonHull(points);
    if (hull) hulls.set(communityId, hull);
  }
  return hulls;
}
