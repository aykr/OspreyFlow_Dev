// Links between communities, drawn instead of individual links on a large working set when zoomed
// out (ADR-119; spec 02 §1.1, §5). Above `COMMUNITY_LINKS_ABOVE` links, the overview and structure
// bands draw one link per pair of communities, its width the number of links it stands for, and the
// individual links appear from the neighbourhood band in. Zoom never changes what exists: the links
// not drawn are still in the working set, counted, searchable and selectable.

import { cachedNodeSvgDataUri } from "../color/nodeVisual";
import type { ZoomBand } from "./zoomBands";

/** Above this many links in the working set, zoomed-out bands draw links between communities. The
 * same number above which a link's weight stops being drawn as width (ADR-097 Amendment 2). */
export const COMMUNITY_LINKS_ABOVE = 10_000;

/** Above this many nodes in the working set, zoomed-out bands draw an ordinary node as a plain dot
 * in its type's colour (ADR-119): drawing 50,000 nodes with their pictures was most of the 50k/250k
 * fixture's first frame. A node that needs its full drawing keeps it (`GlassCanvas.tsx`). */
export const NODE_DOTS_ABOVE = 10_000;

/** Whether ordinary nodes are drawn as dots at this band and size. */
export function drawsNodeDots(band: ZoomBand, nodeCount: number): boolean {
  return nodeCount > NODE_DOTS_ABOVE && (band === "overview" || band === "structure");
}

/** A node's picture when drawn as a dot (Sigma 4: one program draws every node, so a dot is a
 * picture rather than a program of its own): a plain circle in the node's colour, no outline, no
 * icon. One picture per colour, cached. */
export function dotImage(colorHex: string): string {
  return cachedNodeSvgDataUri({ shape: "circle", fillHex: colorHex, strokeHex: colorHex, strokeStyle: "solid", icon: null });
}

/** Whether individual links give way to links between communities at this band and size. */
export function drawsCommunityLinks(band: ZoomBand, linkCount: number): boolean {
  return linkCount > COMMUNITY_LINKS_ABOVE && (band === "overview" || band === "structure");
}

/** One drawn link between two communities, and how many links of the working set it stands for. */
export interface CommunityLink {
  a: number;
  b: number;
  count: number;
}

/** The links between communities: for each pair of different communities, how many links join a
 * member of one to a member of the other. A link inside one community is not counted, and nor is a
 * link with an end the assignment does not know (not yet assigned: drawn as nothing until it is). */
export function communityLinks(
  assignment: ReadonlyMap<string, number>,
  links: Iterable<readonly [string, string]>,
): CommunityLink[] {
  const counts = new Map<string, CommunityLink>();
  for (const [source, target] of links) {
    const a = assignment.get(source);
    const b = assignment.get(target);
    if (a === undefined || b === undefined || a === b) continue;
    const [low, high] = a < b ? [a, b] : [b, a];
    const key = `${low}:${high}`;
    const found = counts.get(key);
    if (found) found.count += 1;
    else counts.set(key, { a: low, b: high, count: 1 });
  }
  return [...counts.values()].sort((x, y) => y.count - x.count || x.a - y.a || x.b - y.b);
}

/** A community link's width in pixels for the number of links it stands for: one link 1px, growing
 * with the logarithm to 6px at a thousand or more, so a busy pair reads heavier without hiding the rest. */
export function communityLinkWidth(count: number): number {
  if (count <= 1) return 1;
  return Math.min(6, 1 + (5 * Math.log10(count)) / 3);
}

/** The group a node's bubble is, from the worker's assignment: its community, or "none" for a node
 * in a community of its own (a node with no links), so all such nodes share one bubble rather than
 * each being a bubble, which would make packing the bubbles slow (it compares every pair). */
export function communityGroupOf(assignment: ReadonlyMap<string, number>): (id: string) => string {
  const sizes = new Map<number, number>();
  for (const community of assignment.values()) sizes.set(community, (sizes.get(community) ?? 0) + 1);
  return (id) => {
    const community = assignment.get(id);
    if (community === undefined || (sizes.get(community) ?? 0) < 2) return "none";
    return `community:${community}`;
  };
}
