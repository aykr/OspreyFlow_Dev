// The graphology working-set store — `spec/02_GLASS_FRONTEND.md` §2's "one
// working set, many views" and §1.1's "zoom never changes what exists,
// only what is drawn".
//
// The graphology `Graph` instance IS the working set. It is deliberately
// kept *outside* the Zustand-managed state tree: graphology mutates a live
// class instance in place and Sigma subscribes to that instance's own
// change events (`nodeAdded`, `edgeDropped`, ...), so routing every
// node/edge write through a second layer's draft/copy cycle would fight
// the exact library ADR-002 chose Sigma to pair with. Zustand here tracks
// only the handful of primitive fields a React component actually needs to
// *react* to — `seq`, `withheld` — never graph membership
// itself. That split is the other half of the zoom/filter separation this
// phase's exit criterion tests: `canvas/zoomBands.ts`'s reducers may read
// graph attributes and this store's `withheld`, but neither may
// mutate the graph, and this module is the *only* place that does.
import Graph from "graphology";
import { createStore, type StoreApi } from "zustand/vanilla";

import type { Edge, Node } from "../../../../packages/schemas/generated";
import type {
  DeltaAdd,
  DeltaRemove,
  DeltaReplaceEdge,
  DeltaReproject,
  DeltaSnapshot,
  WorkingSetDelta,
} from "./models";

/** Every node/edge in the graph carries the full domain object under
 * `data` — that part is this module's own, and the only part
 * `applyDelta` ever touches. The rendering-only fields below (`x`/`y`,
 * `image`, `color`, `borderColor`, `borderSize`) are `canvas/GlassCanvas.
 * tsx`'s: Sigma's custom node programs (`@sigma/node-image`, `@sigma/
 * node-border`) read them directly off the graphology node, not through a
 * reducer's return value (`canvas/nodeAttributes.ts`'s module docstring
 * explains why) — declared here, on the same node type, because they live
 * on the same graphology node, not because this module computes them. */
export type WorkingSetNodeAttributes = {
  data: Node;
  x?: number;
  y?: number;
  image?: string;
  /** The same node with no icon or picture, drawn below the neighbourhood band (ADR-115). */
  imagePlain?: string;
  color?: string;
  borderColor?: string;
  borderSize?: number;
  /** Selected, hovered or on a found path (set with the interaction ring); the canvas names it at
   * any zoom. */
  emphasised?: boolean;
  /** A second, independent `@sigma/node-border` ring (Phase 6a Stage 2) — never the same channel
   * as `borderColor`/`borderSize`'s own interaction-state ring, so a resolution-cluster indicator
   * and a hover/selection/on-path ring can both show at once rather than one silently overriding
   * the other. */
  clusterBorderColor?: string;
  clusterBorderSize?: number;
  /** Selected: drawn larger, with a brass ring and a dark gap of its own (sizes relative to the
   * node's radius), `canvas/nodeAttributes.ts`. */
  selected?: boolean;
  selectionRingColor?: string;
  selectionRingSize?: number;
  selectionGapColor?: string;
  selectionGapSize?: number;
};
export type WorkingSetEdgeAttributes = {
  data: Edge;
  color?: string;
  size?: number;
  label?: string;
  /** Phase 7 Stage 5 (the pathfinder) — merged imperatively by `GlassCanvas`'s own
   * `refreshPathfinderVisualState` whenever the active found path changes, the same
   * merge-onto-stored-attributes shape `WorkingSetNodeAttributes`'s own interaction-state fields
   * already use, so `computeEdgeAttributes` can read it back rather than needing it threaded
   * through the per-frame reducer's own closure. */
  onPath?: boolean;
};
export type WorkingSetGraph = Graph<WorkingSetNodeAttributes, WorkingSetEdgeAttributes>;

export interface WorkingSetStoreState {
  seq: number;
  /** ADR-124 decision 5: the last non-null `DeltaSnapshot.withheld` for the open case; `false`
   * until one says `true`. Never a number. */
  withheld: boolean;
  /** The most recent `reproject` delta, `null` until the first one arrives — a narrower signal
   * than `seq` itself (which changes on every delta) for a consumer that only cares about
   * resolution-cluster changes: `GlassCanvas`'s own cluster-collapse rendering sweep keys off this
   * changing rather than re-scanning the whole working set on every unrelated `add`/`update`. The
   * cluster-collapse sweep reads its `affected_cluster_ids`. The change summary no longer reads
   * it: `ThresholdControl` takes its figures from the answer to its own request. */
  lastReproject: DeltaReproject | null;
  applyDelta: (delta: WorkingSetDelta) => void;
  /** The open case changed: nothing is known of what the next one withholds. */
  resetCase: () => void;
}

export interface WorkingSet {
  /** Bind this exact instance to Sigma — never replace it. */
  graph: WorkingSetGraph;
  /** A vanilla (`zustand/vanilla`) store, deliberately not the React-bound
   * `create` from `"zustand"` — this module has no React dependency, and
   * shouldn't need one just to hold three primitive fields. Checkpoint 2
   * wraps this with `useStore` from `"zustand/react"` wherever an actual
   * component needs to subscribe to it. */
  store: StoreApi<WorkingSetStoreState>;
}

function applyAdd(graph: WorkingSetGraph, delta: DeltaAdd): void {
  for (const node of delta.nodes) {
    if (!graph.hasNode(node.id)) {
      graph.addNode(node.id, { data: node });
    }
  }
  for (const edge of delta.edges) {
    if (!graph.hasEdge(edge.id)) {
      graph.addEdgeWithKey(edge.id, edge.source, edge.target, { data: edge });
    }
  }
}

function applyRemove(graph: WorkingSetGraph, delta: DeltaRemove): void {
  for (const nodeId of delta.node_ids) {
    // graphology drops every incident edge along with the node itself —
    // no separate edge bookkeeping needed here.
    if (graph.hasNode(nodeId)) graph.dropNode(nodeId);
  }
  // A link removed on its own (ADR-124 decision 4): the link goes, its ends stay.
  for (const edgeId of delta.edge_ids ?? []) {
    if (graph.hasEdge(edgeId)) graph.dropEdge(edgeId);
  }
}

function applyReplaceEdge(graph: WorkingSetGraph, delta: DeltaReplaceEdge): void {
  if (graph.hasEdge(delta.old_edge_id)) graph.dropEdge(delta.old_edge_id);
  const edge = delta.edge;
  // A replacement whose ends are not here (another screen's view) has nothing to attach to.
  if (graph.hasEdge(edge.id) || !graph.hasNode(edge.source) || !graph.hasNode(edge.target)) return;
  graph.addEdgeWithKey(edge.id, edge.source, edge.target, { data: edge });
}

function applyReproject(graph: WorkingSetGraph, delta: DeltaReproject): void {
  // `affected_cluster_ids` (Phase 6a Stage 2) is already bounded to the nodes whose membership
  // actually moved — every node currently in the graph gets its `data.resolution.cluster_id`
  // updated in place, the same "nodes merging is a visual event" contract `02_GLASS_FRONTEND.md`'s
  // resolution-cluster rendering reads off this field. A node named here that isn't (yet) in this
  // client's own graph — reached via a different principal's broader view, or a race with a
  // pending `add` — is silently skipped: nothing to annotate until it arrives.
  for (const [nodeId, clusterId] of Object.entries(delta.affected_cluster_ids)) {
    if (!graph.hasNode(nodeId)) continue;
    const current = graph.getNodeAttribute(nodeId, "data");
    graph.setNodeAttribute(nodeId, "data", {
      ...current,
      resolution: { ...current.resolution, cluster_id: clusterId },
    });
  }
}

function applySnapshot(graph: WorkingSetGraph, delta: DeltaSnapshot): void {
  graph.clear();
  for (const node of delta.nodes) {
    graph.addNode(node.id, { data: node });
  }
  for (const edge of delta.edges) {
    graph.addEdgeWithKey(edge.id, edge.source, edge.target, { data: edge });
  }
}

function applyDeltaToGraph(graph: WorkingSetGraph, delta: WorkingSetDelta): void {
  switch (delta.op) {
    case "add":
      applyAdd(graph, delta);
      return;
    case "remove":
      applyRemove(graph, delta);
      return;
    case "replace_edge":
      applyReplaceEdge(graph, delta);
      return;
    case "snapshot":
      applySnapshot(graph, delta);
      return;
    case "reproject":
      // Phase 6a Stage 2: `reproject` never touches working-set *membership* (no node is added
      // or removed), only which cluster each affected node currently belongs to.
      applyReproject(graph, delta);
      return;
    default:
      // A step this client does not know — the retired `notice` among them — touches nothing.
      return;
  }
}

/**
 * The store's own fields after one delta. `withheld` keeps the last non-null value a snapshot
 * carried (ADR-124 decision 5): a `null` or absent field, and every other kind of delta, leave it
 * as it was. A stale server's `filtered_count` and `notice` are never read.
 */
function nextStoreState(
  state: WorkingSetStoreState,
  delta: WorkingSetDelta,
): Pick<WorkingSetStoreState, "seq" | "withheld" | "lastReproject"> {
  const withheld =
    delta.op === "snapshot" && typeof delta.withheld === "boolean" ? delta.withheld : state.withheld;
  return {
    seq: delta.seq,
    withheld,
    lastReproject: delta.op === "reproject" ? delta : state.lastReproject,
  };
}

export function createWorkingSet(): WorkingSet {
  const graph: WorkingSetGraph = new Graph({ multi: true, type: "mixed" });

  const store = createStore<WorkingSetStoreState>((set) => ({
    seq: 0,
    withheld: false,
    lastReproject: null,
    applyDelta: (delta: WorkingSetDelta) => {
      applyDeltaToGraph(graph, delta);
      set((state) => nextStoreState(state, delta));
    },
    resetCase: () => set({ withheld: false }),
  }));

  return { graph, store };
}
