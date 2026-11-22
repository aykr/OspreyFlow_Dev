/**
 * The layouts an analyst can ask for besides the organic force layout (`forceLayout.ts`): radial
 * around a node, layered (hierarchical), circular, grouped by entity type, a force-directed tree
 * and clustered bubbles. Each is a pure
 * function of the nodes and edges it is given, so it is repeatable and testable without a browser.
 *
 * The layered layout is our own, deliberately small (longest-path layers, then a few
 * barycentre sweeps to reduce crossings), behind the same `arrange` interface a library such as
 * dagre could later sit behind (ADR-063). It is not a full Sugiyama implementation: it does not
 * minimise crossings optimally and gives long edges no dummy nodes.
 */

import { settleLayout, type LayoutEdge, type LayoutNode } from "./forceLayout";

export type LayoutMode =
  | "organic"
  | "radial"
  | "hierarchical"
  | "circular"
  | "group"
  | "tree"
  | "bubbles";

export const LAYOUT_MODES: { mode: LayoutMode; label: string }[] = [
  { mode: "organic", label: "Organic" },
  { mode: "radial", label: "Radial around selected node" },
  { mode: "hierarchical", label: "Hierarchical" },
  { mode: "circular", label: "Circular" },
  { mode: "group", label: "Group by type" },
  { mode: "tree", label: "Force-directed tree" },
  { mode: "bubbles", label: "Clustered bubbles" },
];

export interface ArrangeInput {
  nodes: { id: string; type: string; x: number; y: number }[];
  edges: [source: string, target: string][];
}

export interface ArrangeOptions {
  /** For `radial` and `tree`: the node to put in the middle (the tree's root). Falls back to the
   * most connected node. */
  centre?: string | null;
  /** For `bubbles`: which bubble a node belongs to. Falls back to the node's entity type. */
  groupOf?: (id: string) => string;
}

type Placed = Map<string, { x: number; y: number }>;

/** The least distance kept between any two nodes, in world units. */
export const MIN_NODE_GAP = 30;
/** Beyond this many nodes the arrangement is not attempted and `null` is returned. */
export const ARRANGE_MAX_NODES = 6000;

const RING_STEP = 110;
const LAYER_GAP = 100;
const SLOT_GAP = 70;
const SWEEPS = 4;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

function byId(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function cleanEdges(ids: Set<string>, edges: ArrangeInput["edges"]): [string, string][] {
  const seen = new Set<string>();
  const out: [string, string][] = [];
  for (const [a, b] of edges) {
    if (a === b || !ids.has(a) || !ids.has(b)) continue;
    const key = `${a}\u0000${b}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push([a, b]);
  }
  return out;
}

function circular(input: ArrangeInput): Placed {
  const ordered = [...input.nodes].sort((p, q) => byId(p.type, q.type) || byId(p.id, q.id));
  const n = ordered.length;
  const placed: Placed = new Map();
  if (n === 1) {
    placed.set(ordered[0]!.id, { x: 0, y: 0 });
    return placed;
  }
  const radius = Math.max(100, (MIN_NODE_GAP / (2 * Math.sin(Math.PI / n))) * 1.05);
  ordered.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / n;
    placed.set(node.id, { x: radius * Math.cos(angle), y: radius * Math.sin(angle) });
  });
  return placed;
}

function radial(input: ArrangeInput, edges: [string, string][], centreId: string | null | undefined): Placed {
  const ids = input.nodes.map((node) => node.id).sort(byId);
  const neighbours = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const [a, b] of edges) {
    neighbours.get(a)!.push(b);
    neighbours.get(b)!.push(a);
  }
  let centre = centreId && neighbours.has(centreId) ? centreId : null;
  if (centre === null) {
    centre = ids.reduce((best, id) =>
      neighbours.get(id)!.length > neighbours.get(best)!.length ? id : best,
    );
  }
  const placed: Placed = new Map([[centre, { x: 0, y: 0 }]]);
  const angleOf = new Map<string, number>([[centre, 0]]);
  const parentOf = new Map<string, string>();
  let ring = [centre];
  let radius = 0;
  const reached = new Set([centre]);
  while (ring.length > 0) {
    const next: string[] = [];
    for (const id of ring) {
      for (const other of [...neighbours.get(id)!].sort(byId)) {
        if (reached.has(other)) continue;
        reached.add(other);
        parentOf.set(other, id);
        next.push(other);
      }
    }
    if (next.length === 0) break;
    next.sort((p, q) => angleOf.get(parentOf.get(p)!)! - angleOf.get(parentOf.get(q)!)! || byId(p, q));
    radius = Math.max(radius + RING_STEP, (next.length * MIN_NODE_GAP * 1.05) / (2 * Math.PI));
    spread(next, radius, placed, angleOf);
    ring = next;
  }
  const stranded = ids.filter((id) => !reached.has(id));
  if (stranded.length > 0) {
    radius = Math.max(radius + RING_STEP, (stranded.length * MIN_NODE_GAP * 1.05) / (2 * Math.PI));
    spread(stranded, radius, placed, angleOf);
  }
  return placed;
}

function spread(ids: string[], radius: number, placed: Placed, angleOf: Map<string, number>): void {
  ids.forEach((id, i) => {
    const angle = (2 * Math.PI * i) / ids.length;
    angleOf.set(id, angle);
    placed.set(id, { x: radius * Math.cos(angle), y: radius * Math.sin(angle) });
  });
}

/** Edges that close a cycle (found by an iterative depth-first walk) are set aside, so the rest
 * form a graph with no loops that can be put in layers. */
function withoutCycles(ids: string[], edges: [string, string][]): [string, string][] {
  const out = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const [a, b] of edges) out.get(a)!.push(b);
  for (const list of out.values()) list.sort(byId);
  const state = new Map<string, 0 | 1 | 2>(ids.map((id) => [id, 0]));
  const kept: [string, string][] = [];
  for (const start of ids) {
    if (state.get(start) !== 0) continue;
    const stack: { id: string; next: number }[] = [{ id: start, next: 0 }];
    state.set(start, 1);
    while (stack.length > 0) {
      const top = stack[stack.length - 1]!;
      const targets = out.get(top.id)!;
      if (top.next >= targets.length) {
        state.set(top.id, 2);
        stack.pop();
        continue;
      }
      const target = targets[top.next++]!;
      if (state.get(target) === 1) continue; // a back edge: closes a cycle
      kept.push([top.id, target]);
      if (state.get(target) === 0) {
        state.set(target, 1);
        stack.push({ id: target, next: 0 });
      }
    }
  }
  return kept;
}

function hierarchical(input: ArrangeInput, edges: [string, string][]): Placed {
  const ids = input.nodes.map((node) => node.id).sort(byId);
  const dag = withoutCycles(ids, edges);
  const parents = new Map<string, string[]>(ids.map((id) => [id, []]));
  const children = new Map<string, string[]>(ids.map((id) => [id, []]));
  const waiting = new Map<string, number>(ids.map((id) => [id, 0]));
  for (const [a, b] of dag) {
    children.get(a)!.push(b);
    parents.get(b)!.push(a);
    waiting.set(b, waiting.get(b)! + 1);
  }
  // Longest path from any root: a node sits on the layer below its deepest parent.
  const layerOf = new Map<string, number>(ids.map((id) => [id, 0]));
  const queue = ids.filter((id) => waiting.get(id) === 0);
  for (let head = 0; head < queue.length; head++) {
    const id = queue[head]!;
    for (const child of children.get(id)!) {
      layerOf.set(child, Math.max(layerOf.get(child)!, layerOf.get(id)! + 1));
      waiting.set(child, waiting.get(child)! - 1);
      if (waiting.get(child) === 0) queue.push(child);
    }
  }
  const layers: string[][] = [];
  for (const id of ids) {
    const layer = layerOf.get(id)!;
    (layers[layer] ??= []).push(id);
  }
  const x = new Map<string, number>();
  const place = (layer: string[]) => {
    layer.forEach((id, i) => x.set(id, (i - (layer.length - 1) / 2) * SLOT_GAP));
  };
  layers.forEach((layer) => place(layer));
  const sweep = (layer: string[], towards: Map<string, string[]>) => {
    const key = (id: string) => {
      const near = towards.get(id)!;
      return near.length === 0 ? x.get(id)! : near.reduce((s, other) => s + x.get(other)!, 0) / near.length;
    };
    const keyed = layer.map((id, i) => ({ id, i, k: key(id) }));
    keyed.sort((p, q) => p.k - q.k || p.i - q.i);
    layer.splice(0, layer.length, ...keyed.map((entry) => entry.id));
    place(layer);
  };
  for (let pass = 0; pass < SWEEPS; pass++) {
    for (let l = 1; l < layers.length; l++) sweep(layers[l]!, parents);
    for (let l = layers.length - 2; l >= 0; l--) sweep(layers[l]!, children);
  }
  const placed: Placed = new Map();
  for (const id of ids) placed.set(id, { x: x.get(id)!, y: layerOf.get(id)! * LAYER_GAP });
  return placed;
}

function grouped(input: ArrangeInput): Placed {
  const byType = new Map<string, string[]>();
  for (const node of input.nodes) {
    const list = byType.get(node.type) ?? [];
    list.push(node.id);
    byType.set(node.type, list);
  }
  const spacing = MIN_NODE_GAP * 1.25;
  const groups = [...byType.entries()]
    .map(([type, members]) => ({
      type,
      members: members.sort(byId),
      radius: spacing * Math.sqrt(members.length) + MIN_NODE_GAP / 2,
    }))
    .sort((p, q) => q.members.length - p.members.length || byId(p.type, q.type));
  const between = 2 * MIN_NODE_GAP;
  const area = groups.reduce((s, g) => s + (2 * g.radius + between) ** 2, 0);
  const rowWidth = Math.max(Math.sqrt(area) * 1.2, 2 * groups[0]!.radius + between);
  const placed: Placed = new Map();
  let cursorX = 0;
  let cursorY = 0;
  let rowHeight = 0;
  for (const group of groups) {
    const size = 2 * group.radius;
    if (cursorX > 0 && cursorX + size > rowWidth) {
      cursorX = 0;
      cursorY += rowHeight + between;
      rowHeight = 0;
    }
    const cx = cursorX + group.radius;
    const cy = cursorY + group.radius;
    group.members.forEach((id, i) => {
      const r = spacing * Math.sqrt(i + 0.5);
      const angle = i * GOLDEN_ANGLE;
      placed.set(id, { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) });
    });
    cursorX += size + between;
    rowHeight = Math.max(rowHeight, size);
  }
  return placed;
}


// ---------------------------------------------------------------------------------------------
// Force-directed tree. Only the links of a tree (a shortest-path tree from the root, so a link that
// would close a loop is left out) pull nodes together; every node pushes the others away. The
// start is a radial tree, so the same graph always settles the same way, and a graph too large to
// settle (`FORCE_LAYOUT_MAX_NODES`) is left as that radial tree rather than not arranged at all.
// ---------------------------------------------------------------------------------------------

const TREE_STEP = 70;
const VIRTUAL_ROOT = "\u0000root";

/** The key of a link, the same whichever end is named first. */
export function linkKey(a: string, b: string): string {
  return a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`;
}

interface Forest {
  parent: Map<string, string | null>;
  order: string[];
  roots: string[];
}

function forestOf(ids: string[], edges: [string, string][], centreId: string | null | undefined): Forest {
  const neighbours = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const [a, b] of edges) {
    neighbours.get(a)!.push(b);
    neighbours.get(b)!.push(a);
  }
  for (const list of neighbours.values()) list.sort(byId);
  const parent = new Map<string, string | null>();
  const order: string[] = [];
  const roots: string[] = [];
  const grow = (root: string) => {
    roots.push(root);
    parent.set(root, null);
    const queue = [root];
    for (let head = 0; head < queue.length; head++) {
      const id = queue[head]!;
      for (const other of neighbours.get(id)!) {
        if (parent.has(other)) continue;
        parent.set(other, id);
        queue.push(other);
      }
    }
    order.push(...queue);
  };
  if (centreId && neighbours.has(centreId)) grow(centreId);
  // Each piece the root does not reach is rooted on its most linked node.
  const busiest = [...ids].sort((p, q) => neighbours.get(q)!.length - neighbours.get(p)!.length || byId(p, q));
  for (const id of busiest) if (!parent.has(id)) grow(id);
  return { parent, order, roots };
}

/**
 * The links that make up the tree for these nodes and this root, by `linkKey`. Links not in it are
 * the ones a tree layout does not use; the canvas draws them faint.
 */
export function treeLinkKeys(input: ArrangeInput, centre?: string | null): Set<string> {
  const ids = input.nodes.map((node) => node.id).sort(byId);
  const edges = cleanEdges(new Set(ids), input.edges);
  const { parent } = forestOf(ids, edges, centre);
  const keys = new Set<string>();
  for (const [id, up] of parent) if (up !== null) keys.add(linkKey(id, up));
  return keys;
}

function forceTree(input: ArrangeInput, edges: [string, string][], centreId: string | null | undefined): Placed {
  const ids = input.nodes.map((node) => node.id).sort(byId);
  const { parent, order, roots } = forestOf(ids, edges, centreId);
  const top = roots.length === 1 ? roots[0]! : VIRTUAL_ROOT;
  const children = new Map<string, string[]>([[top, []]]);
  for (const id of ids) children.set(id, []);
  const depth = new Map<string, number>([[top, 0]]);
  for (const id of order) {
    const up = parent.get(id) ?? null;
    if (up === null) {
      if (id === top) continue;
      children.get(top)!.push(id);
      depth.set(id, 1);
    } else {
      children.get(up)!.push(id);
      depth.set(id, depth.get(up)! + 1);
    }
  }
  const leaves = new Map<string, number>();
  for (let i = order.length - 1; i >= -1; i--) {
    const id = i === -1 ? top : order[i]!;
    if (id === top && i !== -1) continue;
    const kids = children.get(id)!;
    leaves.set(id, kids.length === 0 ? 1 : kids.reduce((sum, kid) => sum + leaves.get(kid)!, 0));
  }
  // A radial tree: each node takes a slice of its parent's angle in proportion to its leaves.
  const start: Placed = new Map();
  const sector = new Map<string, [number, number]>([[top, [0, 2 * Math.PI]]]);
  const stack = [top];
  while (stack.length > 0) {
    const id = stack.pop()!;
    const [from, to] = sector.get(id)!;
    const mid = (from + to) / 2;
    const r = depth.get(id)! * TREE_STEP;
    start.set(id, { x: r * Math.cos(mid), y: r * Math.sin(mid) });
    let cursor = from;
    const total = leaves.get(id)!;
    for (const kid of children.get(id)!) {
      const share = ((to - from) * leaves.get(kid)!) / total;
      sector.set(kid, [cursor, cursor + share]);
      cursor += share;
      stack.push(kid);
    }
  }
  const nodes: LayoutNode[] = [...start].map(([id, at]) => ({
    id,
    x: at.x,
    y: at.y,
    pinned: id === VIRTUAL_ROOT,
  }));
  const links: LayoutEdge[] = [];
  for (const [id, up] of parent) links.push([up ?? top, id]);
  const settled = settleLayout(nodes, links) ?? start;
  const placed: Placed = new Map();
  for (const id of ids) placed.set(id, settled.get(id)!);
  return placed;
}

// ---------------------------------------------------------------------------------------------
// Clustered bubbles. One bubble for each group, the group's nodes packed inside it, and the bubbles
// themselves packed against one another without overlapping, the largest in the middle.
// ---------------------------------------------------------------------------------------------

const BUBBLE_PAD = 24;
const BUBBLE_GAP = 24;

/** Clustered bubbles with no size limit: linear in the nodes, and in the groups squared, so a
 * caller with many nodes must keep the groups few (ADR-119 puts every node in no community into one
 * group). Used for a large working set grouped by community from the worker (`communityLinks.ts`). */
export function packBubbles(input: ArrangeInput, groupOf: (id: string) => string): Map<string, { x: number; y: number }> {
  return bubbles(input, groupOf);
}

function bubbles(input: ArrangeInput, groupOf: ((id: string) => string) | undefined): Placed {
  const byGroup = new Map<string, string[]>();
  for (const node of input.nodes) {
    const key = groupOf ? groupOf(node.id) : node.type;
    const list = byGroup.get(key) ?? [];
    list.push(node.id);
    byGroup.set(key, list);
  }
  const spacing = MIN_NODE_GAP * 1.25;
  const groups = [...byGroup.entries()]
    .map(([key, members]) => ({
      key,
      members: members.sort(byId),
      radius: spacing * Math.sqrt(members.length) + MIN_NODE_GAP / 2 + BUBBLE_PAD,
    }))
    .sort((p, q) => q.members.length - p.members.length || byId(p.key, q.key));
  const centres: { x: number; y: number; radius: number }[] = [];
  const placed: Placed = new Map();
  for (const group of groups) {
    let centre = { x: 0, y: 0 };
    if (centres.length > 0) {
      // Walk outwards along a spiral to the first spot where this bubble clears every other.
      for (let step = 1; ; step++) {
        const angle = step * 0.31;
        const r = step * 2.5;
        centre = { x: r * Math.cos(angle), y: r * Math.sin(angle) };
        if (centres.every((c) => Math.hypot(c.x - centre.x, c.y - centre.y) >= c.radius + group.radius + BUBBLE_GAP)) break;
      }
    }
    centres.push({ ...centre, radius: group.radius });
    group.members.forEach((id, i) => {
      const r = spacing * Math.sqrt(i + 0.5);
      const angle = i * GOLDEN_ANGLE;
      placed.set(id, { x: centre.x + r * Math.cos(angle), y: centre.y + r * Math.sin(angle) });
    });
  }
  return placed;
}

/** The smallest circle round the middle of some points that holds them all, with `pad` to spare:
 * the bubble the canvas draws round a group, worked out from where its nodes are drawn now. */
export function enclosingCircle(
  points: readonly { x: number; y: number }[],
  pad: number,
): { x: number; y: number; r: number } {
  if (points.length === 0) return { x: 0, y: 0, r: pad };
  const x = points.reduce((sum, p) => sum + p.x, 0) / points.length;
  const y = points.reduce((sum, p) => sum + p.y, 0) / points.length;
  const r = Math.max(...points.map((p) => Math.hypot(p.x - x, p.y - y))) + pad;
  return { x, y, r };
}

/**
 * Positions for every node, by id; `null` when the graph is too large to arrange quickly (the
 * caller keeps the positions it has). `organic` is not handled here: it is the force layout.
 */
export function arrange(
  mode: Exclude<LayoutMode, "organic">,
  input: ArrangeInput,
  options: ArrangeOptions = {},
): Placed | null {
  if (input.nodes.length > ARRANGE_MAX_NODES) return null;
  if (input.nodes.length === 0) return new Map();
  const ids = new Set(input.nodes.map((node) => node.id));
  const edges = cleanEdges(ids, input.edges);
  switch (mode) {
    case "circular":
      return circular(input);
    case "radial":
      return radial(input, edges, options.centre);
    case "hierarchical":
      return hierarchical(input, edges);
    case "group":
      return grouped(input);
    case "tree":
      return forceTree(input, edges, options.centre);
    case "bubbles":
      return bubbles(input, options.groupOf);
  }
}
