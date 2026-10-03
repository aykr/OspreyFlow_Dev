// Communities on screen (ADR-066): find groups of closely linked nodes among the nodes now in the
// view, draw a box round each, and let the analyst fold one into a single Group Node and open it
// again. Everything here is pure arithmetic on ids and positions. Nothing is stored and nothing is
// sent to the server: it is a way of looking at the view, and it is undone by clearing the state.
import Graph from "graphology";
import louvain from "graphology-communities-louvain";

export interface Community {
  /** `c:` plus the smallest member id, so the name survives a re-run on the same nodes. */
  id: string;
  members: string[];
}

export interface Box {
  id: string;
  count: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface Point {
  x: number;
  y: number;
}

/** A small seeded generator, so the same nodes always fall into the same groups. */
function seededRandom(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const LOUVAIN_SEED = 20260929;

/**
 * Louvain over the nodes given and the links between them. A link to a node not in `nodeIds`, a
 * link to self, and repeated links are tolerated (repeats add weight). A node with no neighbour is
 * never reported as a community of its own. Largest community first; members sorted.
 */
export function findCommunities(
  nodeIds: readonly string[],
  edges: readonly (readonly [string, string])[],
): Community[] {
  const present = new Set(nodeIds);
  const graph = new Graph({ type: "undirected", multi: false });
  for (const id of nodeIds) graph.mergeNode(id);
  for (const [a, b] of edges) {
    if (a === b || !present.has(a) || !present.has(b)) continue;
    if (graph.hasEdge(a, b)) {
      graph.updateEdgeAttribute(a, b, "weight", (w: number | undefined) => (w ?? 1) + 1);
    } else {
      graph.addEdge(a, b, { weight: 1 });
    }
  }
  if (graph.size === 0) return [];

  const assignment = louvain(graph, { getEdgeWeight: "weight", rng: seededRandom(LOUVAIN_SEED) });
  const byIndex = new Map<number, string[]>();
  for (const [id, index] of Object.entries(assignment)) {
    const list = byIndex.get(index);
    if (list) list.push(id);
    else byIndex.set(index, [id]);
  }
  const found: Community[] = [];
  for (const members of byIndex.values()) {
    if (members.length < 2) continue;
    members.sort();
    found.push({ id: `c:${members[0]}`, members });
  }
  found.sort((a, b) => b.members.length - a.members.length || a.id.localeCompare(b.id));
  return found;
}

export function communityOf(communities: readonly Community[], nodeId: string): Community | null {
  return communities.find((c) => c.members.includes(nodeId)) ?? null;
}

/** One box per community that still has at least two positioned members, grown by `padding`. */
export function communityBoxes(
  communities: readonly Community[],
  positions: ReadonlyMap<string, Point>,
  padding: number,
): Box[] {
  const boxes: Box[] = [];
  for (const community of communities) {
    let x0 = Infinity;
    let y0 = Infinity;
    let x1 = -Infinity;
    let y1 = -Infinity;
    let count = 0;
    for (const id of community.members) {
      const at = positions.get(id);
      if (!at) continue;
      count += 1;
      x0 = Math.min(x0, at.x);
      y0 = Math.min(y0, at.y);
      x1 = Math.max(x1, at.x);
      y1 = Math.max(y1, at.y);
    }
    if (count < 2) continue;
    boxes.push({
      id: community.id,
      count,
      x0: x0 - padding,
      y0: y0 - padding,
      x1: x1 + padding,
      y1: y1 + padding,
    });
  }
  return boxes;
}

/** The box under a point (edges count as inside); the smallest when several overlap. */
export function boxAt(boxes: readonly Box[], x: number, y: number): Box | null {
  let best: Box | null = null;
  let bestArea = Infinity;
  for (const box of boxes) {
    if (x < box.x0 || x > box.x1 || y < box.y0 || y > box.y1) continue;
    const area = (box.x1 - box.x0) * (box.y1 - box.y0);
    if (area < bestArea) {
      best = box;
      bestArea = area;
    }
  }
  return best;
}

/** "Group of 4 nodes: Account 3, Person 1": the commonest types first, three at most. */
export function groupLabel(types: readonly string[]): string {
  const counts = new Map<string, number>();
  for (const type of types) counts.set(type, (counts.get(type) ?? 0) + 1);
  const ordered = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const shown = ordered.slice(0, 3).map(([type, n]) => `${type} ${n}`);
  const rest = ordered.slice(3).length;
  if (rest > 0) shown.push(`${rest} other`);
  const noun = types.length === 1 ? "node" : "nodes";
  return `Group of ${types.length} ${noun}: ${shown.join(", ")}`;
}

export interface GroupStandIn {
  communityId: string;
  count: number;
  /** Where the group is drawn: the centre of its members. */
  x: number;
  y: number;
  label: string;
}

export interface CollapsedView {
  /** The member drawn as the Group Node, by its own id. */
  groups: Map<string, GroupStandIn>;
  /** Members that are not drawn while their group is folded. */
  hidden: Set<string>;
  /** Every node inside a folded group, the stand-in included. */
  groupedNodeCount: number;
  /** A link between two members of one folded group is not drawn. */
  hidesLink: (a: string, b: string) => boolean;
  /** Where a hidden member is drawn while its group is folded (the group's centre), so a link from
   * outside to it still reaches the group; `null` for anything not hidden. */
  anchorOf: (id: string) => Point | null;
}

/**
 * What the canvas should draw for the groups folded in `collapsed`. The most connected member
 * (the smaller id on a tie) stands in for the group at the centre of its members, so every link
 * from outside still reaches the group, and the underlying nodes and their positions are never
 * touched. An id in `collapsed` that names no community is ignored.
 */
export function collapseView(
  communities: readonly Community[],
  collapsed: ReadonlySet<string>,
  positions: ReadonlyMap<string, Point>,
  degreeOf: (id: string) => number,
  typeOf: (id: string) => string,
): CollapsedView {
  const groups = new Map<string, GroupStandIn>();
  const hidden = new Set<string>();
  const folded = new Map<string, string>(); // member -> community id
  const anchors = new Map<string, Point>(); // hidden member -> its group's centre
  let groupedNodeCount = 0;
  for (const community of communities) {
    if (!collapsed.has(community.id)) continue;
    let standIn = community.members[0]!;
    for (const id of community.members) {
      folded.set(id, community.id);
      const better =
        degreeOf(id) > degreeOf(standIn) || (degreeOf(id) === degreeOf(standIn) && id < standIn);
      if (better) standIn = id;
    }
    let sx = 0;
    let sy = 0;
    let located = 0;
    for (const id of community.members) {
      const at = positions.get(id);
      if (!at) continue;
      sx += at.x;
      sy += at.y;
      located += 1;
    }
    const centre = located > 0 ? { x: sx / located, y: sy / located } : { x: 0, y: 0 };
    groups.set(standIn, {
      communityId: community.id,
      count: community.members.length,
      x: centre.x,
      y: centre.y,
      label: groupLabel(community.members.map(typeOf)),
    });
    for (const id of community.members) {
      if (id === standIn) continue;
      hidden.add(id);
      anchors.set(id, { x: centre.x, y: centre.y });
    }
    groupedNodeCount += community.members.length;
  }
  return {
    groups,
    hidden,
    groupedNodeCount,
    hidesLink: (a, b) => {
      const ca = folded.get(a);
      return ca !== undefined && ca === folded.get(b);
    },
    anchorOf: (id) => anchors.get(id) ?? null,
  };
}

/** Drops folded ids whose community is gone; returns the same set when none had to go. */
export function reconcileCollapsed(
  collapsed: ReadonlySet<string>,
  communities: readonly Community[],
): ReadonlySet<string> {
  const live = new Set(communities.map((c) => c.id));
  const kept = [...collapsed].filter((id) => live.has(id));
  return kept.length === collapsed.size ? collapsed : new Set(kept);
}
