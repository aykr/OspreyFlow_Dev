// The Sigma-bound canvas — `docs/02_GLASS_FRONTEND.md` §1/§1.1,
// `docs/07_BUILD_PLAN.md` Phase 4 Checkpoint 2: "Sigma renderer with the
// full node state vocabulary... Canvas interaction: pan, zoom, select,
// lasso, radial context menu, expand... Semantic zoom."
//
// Node shape/fill/provenance is `@sigma/node-image` (a generated SVG per
// distinct combination, `color/nodeVisual.ts`); the interaction-state ring
// is a composed `@sigma/node-border` layer. Both plugins read their own
// attributes directly off the graphology node (`workingset/store.ts`'s
// `WorkingSetNodeAttributes`) — `canvas/nodeAttributes.ts`'s module
// docstring explains why that is not the `nodeReducer`'s job.
//
// **Known simplifications, disclosed rather than silent:**
// - Edges render with Sigma's plain `EdgeLineProgram` (straight lines).
//   `@sigma/edge-curve`'s curved-parallel-edges at the Neighbourhood/
//   Link-detail bands (§1.1's table) is installed but not yet wired — a
//   visual refinement, not a correctness requirement this phase's exit
//   criterion tests.
// - Initial layout is a deterministic pseudo-random scatter, not
//   ForceAtlas2 in a worker (§5's own performance technique). A real
//   force layout is real engineering work of its own; wiring one in
//   without being able to profile it against the 50k/250k fixture in this
//   environment would be guessing at the number that actually matters.
import { createNodeBorderProgram } from "@sigma/node-border";
import { createNodeImageProgram } from "@sigma/node-image";
import type { StoreApi } from "zustand/vanilla";
import { useStore } from "zustand/react";
import { EdgeLineProgram, createNodeCompoundProgram } from "sigma/rendering";
import Sigma from "sigma";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

import type { Edge, EdgeTypeDef, Node, Path as GraphPath } from "../../../../packages/schemas/generated";
import { pointInPolygon } from "../map/geometry";
import type { OntologyRegistry } from "../ontology/schema";
import type {
  WorkingSetEdgeAttributes,
  WorkingSetGraph,
  WorkingSetNodeAttributes,
  WorkingSetStoreState,
} from "../workingset/store";
import {
  computeClusterGraphAttributes,
  computeEdgeAttributes,
  computeNodeFrameAttributes,
  computeNodeGraphAttributes,
} from "./nodeAttributes";
import { RadialMenu, type RadialMenuItem } from "../design/primitives/RadialMenu";
import { EdgeInspectionOverlay } from "./EdgeInspectionOverlay";
import { ClusterExplainOverlay } from "./ClusterExplainOverlay";
import { CommunityHullOverlay } from "./CommunityHullOverlay";
import { PathfinderOverlay } from "./PathfinderOverlay";
import { PathfinderErrorOverlay } from "./PathfinderErrorOverlay";
import type { ClusterExplanation } from "../workingset/models";

const NODE_PROGRAM = createNodeCompoundProgram<WorkingSetNodeAttributes, WorkingSetEdgeAttributes>([
  createNodeImageProgram<WorkingSetNodeAttributes, WorkingSetEdgeAttributes>({
    keepWithinCircle: false,
    drawingMode: "background",
    padding: 0,
  }),
  createNodeBorderProgram<WorkingSetNodeAttributes, WorkingSetEdgeAttributes>({
    borders: [
      // Resolution-cluster ring (Phase 6a Stage 2) drawn first/innermost, so the interaction-state
      // ring below it — on-path/selected/hover, which changes far more often — stays the outer,
      // more prominent one. Independent attribute channel: a clustered node can be selected too.
      {
        color: { attribute: "clusterBorderColor" },
        size: { attribute: "clusterBorderSize", defaultValue: 0, mode: "pixels" },
      },
      {
        color: { attribute: "borderColor" },
        size: { attribute: "borderSize", defaultValue: 0, mode: "pixels" },
      },
    ],
  }),
]);

function seededScatter(nodeId: string): { x: number; y: number } {
  // A cheap, deterministic hash — the same id always lands at the same
  // point, so a reconnect/resnapshot doesn't jump every node around.
  let hash = 0;
  for (let i = 0; i < nodeId.length; i++) hash = (hash * 31 + nodeId.charCodeAt(i)) | 0;
  const angle = ((hash >>> 0) % 3600) / 3600 * 2 * Math.PI;
  const radius = 50 + (((hash >>> 8) >>> 0) % 400);
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

export interface GlassCanvasProps {
  graph: WorkingSetGraph;
  store: StoreApi<WorkingSetStoreState>;
  ontology: OntologyRegistry;
  edgeTypes: EdgeTypeDef[];
  investigationId: string;
  apiBaseUrl: string;
  bearerToken: string;
  /** Node ids the active cross-filter excludes (`crossfilter/store.ts`) —
   * dimmed, never removed, per `docs/02_GLASS_FRONTEND.md` §2 rule 2.
   * Defaults to an empty set so this prop stays optional for any caller
   * that hasn't wired cross-filtering (e.g. an existing test harness). */
  dimmedNodeIds?: ReadonlySet<string>;
  onSelectionChange?: (nodeIds: string[]) => void;
  /** The keyboard-focused node id (`docs/02_GLASS_FRONTEND.md` §6: "Tab
   * moves between nodes... arrow keys walk edges"), or `null` when
   * nothing has been keyboard-focused yet. Exposed so a caller can, e.g.,
   * highlight the focused node in a legend — and it is what
   * `keyboard/keyboard.spec.ts` observes to prove the keyboard-only
   * walkthrough actually moves focus, rather than asserting on internal
   * component state it has no other way to reach. */
  onFocusChange?: (nodeId: string | null) => void;
  /** B6 / Phase 6a Stage 4: the "View messages" radial-menu item (`Endpoint`-type nodes only,
   * `08_ACCEPTANCE_SCENARIOS.md` B6's own wording — "the shared endpoint's messages") calls this
   * with the node's own id rather than owning any Dossier state itself; `App.tsx` owns `view`,
   * the same separation `onSelectionChange` already establishes. */
  onViewMessages?: (nodeId: string) => void;
  /** Phase 7 Stage 3: the metrics panel's own community-detection result, already grouped into
   * hull polygons by `metrics/hulls.ts`'s pure `computeCommunityHulls` — `GlassCanvas` only
   * renders them (`CommunityHullOverlay`, camera-tracked the same way `EdgeInspectionOverlay`'s
   * own DOM-overlay pattern is, ADR-002's "one honest caveat"), it does not compute them, so a
   * caller that never fetches communities pays nothing beyond the `undefined` check below. */
  communityHulls?: ReadonlyMap<string, readonly [number, number][]>;
}

/** Phase 7 Stage 3: what the metrics panel needs from outside the canvas's own event handlers —
 * "row-select-and-centre" is real application logic (a camera pan, not merely a browser default),
 * so it is proven end-to-end by `keyboard/metrics-panel.spec.ts`, per standing rule 13. */
export interface GlassCanvasHandle {
  /** Selects `nodeId` (firing `onSelectionChange`/`onFocusChange` exactly as a mouse click would)
   * and pans the camera to centre it, without changing the current zoom ratio — a no-op if
   * `nodeId` is not in `graph` (e.g. a stale metrics-panel row after a working-set change). */
  focusOnNode: (nodeId: string) => void;
}

interface PendingRadialMenu {
  x: number;
  y: number;
  nodeId: string;
  layout: "radial" | "list";
}

// A stable reference, not `new Set()` inline in a default parameter — the
// same reason `App.tsx`'s `EMPTY_NODE_COORDINATES` exists: a fresh Set on
// every render would change `dimmedNodeIds`' identity every time, and it
// feeds a `useEffect` dependency array below (found and fixed once this
// phase as a real infinite-render bug in `MapView`'s own `nodeCoordinates`
// prop, not a hypothetical this time either).
const EMPTY_DIMMED_SET: ReadonlySet<string> = new Set();

export const GlassCanvas = forwardRef<GlassCanvasHandle, GlassCanvasProps>(function GlassCanvas(
  {
    graph,
    store,
    ontology,
    edgeTypes,
    investigationId,
    apiBaseUrl,
    bearerToken,
    dimmedNodeIds = EMPTY_DIMMED_SET,
    onSelectionChange,
    onFocusChange,
    onViewMessages,
    communityHulls,
  }: GlassCanvasProps,
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  useEffect(() => {
    onFocusChange?.(focused);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focused]);
  const [radialMenu, setRadialMenu] = useState<PendingRadialMenu | null>(null);
  const [inspectedEdge, setInspectedEdge] = useState<{ edgeId: string; x: number; y: number } | null>(
    null,
  );
  const [clusterExplain, setClusterExplain] = useState<
    { x: number; y: number; explanation: ClusterExplanation } | null
  >(null);
  // Phase 7 Stage 5 (the pathfinder) — `x`/`y` anchor the overlay to the radial menu's own
  // position, the same shape `clusterExplain` above already uses. `activeIndex` is which of the
  // (up to `k`) found paths is currently drawn on-path; cycling it never re-fetches.
  const [pathResult, setPathResult] = useState<
    { x: number; y: number; paths: GraphPath[]; activeIndex: number } | null
  >(null);
  // A failed `/v1/paths` call — distinguishable from `pathResult`'s own "No path found" (a
  // completed search, zero results) rather than folded into it, since the two are different
  // findings for the analyst (`findPaths`'s own doc comment below has the full reasoning).
  const [pathError, setPathError] = useState<{ x: number; y: number; message: string } | null>(
    null,
  );
  // Read by `refreshNodeVisualState` (called from many unrelated call sites — hover, selection,
  // dimming) without threading a new parameter through every one of them; written only by the
  // effect below, keyed on `pathResult` itself. A ref, not state, because nothing here needs a
  // re-render when it changes on its own — the effect that writes it already re-renders via
  // `pathResult`.
  const pathNodeIdsRef = useRef<Set<string>>(new Set());
  const [lassoActive, setLassoActive] = useState(false);
  const [lassoPoints, setLassoPoints] = useState<{ x: number; y: number }[]>([]);
  const lastReproject = useStore(store, (s) => s.lastReproject);

  const refreshNodeVisualState = (nodeId: string) => {
    if (!graph.hasNode(nodeId)) return;
    const node = graph.getNodeAttribute(nodeId, "data");
    const visual = ontology.visualFor(node.type);
    if (!visual) return;
    const onPath = pathNodeIdsRef.current.has(nodeId);
    // `02_GLASS_FRONTEND.md` §3.1: "everything else dims to 32%" — a found path in effect adds a
    // second, independent reason a node can be dimmed, ORed with the existing cross-filter
    // dimming rather than replacing it.
    const pathActive = pathNodeIdsRef.current.size > 0;
    const attrs = computeNodeGraphAttributes(node, visual, {
      dimmed: dimmedNodeIds.has(nodeId) || (pathActive && !onPath),
      filteredOut: false,
      hovered: hovered === nodeId,
      selected: selected.has(nodeId),
      onPath,
    });
    graph.mergeNodeAttributes(nodeId, attrs);
  };

  // Re-derives which nodes/edges are "on path" whenever the found path or the analyst's choice of
  // which of the `k` results to look at changes, and refreshes every node/edge's own visual state
  // accordingly — dimming is a whole-graph property of "a path is active," not a per-node toggle,
  // so this sweeps the graph the same way `refreshClusterVisualState` does for its own trigger.
  useEffect(() => {
    const activePath = pathResult ? pathResult.paths[pathResult.activeIndex] : undefined;
    pathNodeIdsRef.current = new Set(activePath?.nodes.map((n) => n.id) ?? []);
    const pathEdgeIds = new Set(activePath?.edges.map((e) => e.id) ?? []);
    graph.forEachNode((nodeId) => refreshNodeVisualState(nodeId));
    graph.forEachEdge((edgeId) => {
      graph.mergeEdgeAttributes(edgeId, { onPath: pathEdgeIds.has(edgeId) });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathResult, graph]);

  // Phase 6a Stage 2 (B9): "the number and the picture have to agree" — every node sharing a
  // `resolution.cluster_id` with at least one other is co-located at the cluster's own anchor
  // (`compute_clusters`' union-find convention: the cluster id *is* one of its own member ids, the
  // numerically-smallest one) and gets the second, dedicated cluster-ring attributes. A node no
  // longer (or never) merged gets its own deterministic `seededScatter` home position back —
  // recomputed on demand rather than stored, so an un-merge (raising τ back up) has a real
  // position to return to instead of staying wherever a previous merge last placed it.
  const refreshClusterVisualState = () => {
    const membersByCluster = new Map<string, string[]>();
    graph.forEachNode((nodeId, attrs) => {
      const clusterId = attrs.data.resolution?.cluster_id ?? nodeId;
      const members = membersByCluster.get(clusterId);
      if (members) members.push(nodeId);
      else membersByCluster.set(clusterId, [nodeId]);
    });
    for (const [clusterId, members] of membersByCluster) {
      const clusterAttrs = computeClusterGraphAttributes(members.length);
      for (const nodeId of members) {
        graph.mergeNodeAttributes(nodeId, clusterAttrs);
        if (nodeId === clusterId) continue;
        const anchorX = members.length > 1 ? graph.getNodeAttribute(clusterId, "x") : undefined;
        const anchorY = members.length > 1 ? graph.getNodeAttribute(clusterId, "y") : undefined;
        if (anchorX !== undefined && anchorY !== undefined) {
          graph.mergeNodeAttributes(nodeId, { x: anchorX, y: anchorY });
        } else {
          const home = seededScatter(nodeId);
          graph.mergeNodeAttributes(nodeId, { x: home.x, y: home.y });
        }
      }
    }
  };

  // Assign an initial position and the graph-level (rarely-changing)
  // visual attributes exactly once, when a node is added to the working
  // set — never inside the per-frame reducer.
  useEffect(() => {
    const onNodeAdded = ({ key }: { key: string }) => {
      if (graph.getNodeAttribute(key, "x") === undefined) {
        const { x, y } = seededScatter(key);
        graph.mergeNodeAttributes(key, { x, y });
      }
      refreshNodeVisualState(key);
    };
    graph.on("nodeAdded", onNodeAdded);
    // Nodes already present (e.g. the initial snapshot arrived before
    // this effect ran) still need their first pass.
    graph.forEachNode((key) => onNodeAdded({ key }));
    return () => {
      graph.removeListener("nodeAdded", onNodeAdded);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  // Cluster-collapse rendering: runs once every node has its initial `seededScatter` position
  // (this effect is declared, and therefore runs, after the one above), and again only when a
  // `reproject` delta actually lands — `lastReproject` is `WorkingSetStoreState`'s own narrower
  // signal for exactly that, so an unrelated `add`/`update` delta doesn't trigger a working-set-wide
  // sweep for nothing.
  useEffect(() => {
    refreshClusterVisualState();
    sigmaRef.current?.scheduleRefresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, lastReproject]);

  // Re-derive graph-level visual attributes only for the node(s) whose
  // hover/selection actually changed — not the whole working set.
  useEffect(() => {
    graph.forEachNode((key) => {
      const wasSelected = selected.has(key);
      const isHovered = hovered === key;
      if (wasSelected || isHovered || graph.getNodeAttribute(key, "borderSize")) {
        refreshNodeVisualState(key);
      }
    });
    sigmaRef.current?.scheduleRefresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, hovered]);

  // A cross-filter update can dim or un-dim *any* node in the working set,
  // not just ones already selected/hovered/bordered — unlike the effect
  // above, this one has to sweep every node rather than skip most of them.
  useEffect(() => {
    graph.forEachNode((key) => refreshNodeVisualState(key));
    sigmaRef.current?.scheduleRefresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dimmedNodeIds]);

  useEffect(() => {
    if (!containerRef.current) return;
    // `Sigma`'s own constructor calls `refresh()` synchronously — which,
    // for a graph that already has nodes at mount time (a history
    // restore, a branch, or this checkpoint's own perf-fixture harness —
    // not the ordinary empty-investigation-then-stream-fills-it path this
    // bug's absence from earlier manual testing traces to), invokes
    // `nodeReducer` *during construction*, before `const sigma = new
    // Sigma(...)` has finished assigning. Referencing `sigma` directly
    // inside the reducer is therefore a real TDZ crash, not a hypothetical
    // one: `let currentSigma`, assigned right after construction, gives
    // the reducer a binding that exists (as `undefined`) through that
    // first synchronous pass instead.
    // eslint-disable-next-line prefer-const -- must exist (as `undefined`) before `new Sigma(...)` runs; a `const` at the single later assignment would reintroduce the TDZ bug above.
    let currentSigma: Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | undefined;
    const sigma = new Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes>(graph, containerRef.current, {
      defaultNodeType: "glass-node",
      nodeProgramClasses: { "glass-node": NODE_PROGRAM },
      defaultEdgeType: "glass-edge",
      edgeProgramClasses: { "glass-edge": EdgeLineProgram },
      // Sigma's own `addNode`/`updateNode`: "this function must return a
      // total object and won't be merged" with the raw graph attributes —
      // a reducer's return *replaces* them entirely for every downstream
      // consumer, including `@sigma/node-image`/`@sigma/node-border`'s own
      // `data[imageAttribute]`/`data["borderColor"]` reads. So `...data`
      // (the raw attributes, shallow-copied by Sigma before calling this)
      // must be spread through first — only the frame-computed fields
      // actually need to *override* anything. Discovered by an empty
      // canvas: omitting this leaves every custom-program attribute
      // `undefined`, silently, not by reasoning about the library's
      // source ahead of time.
      nodeReducer: (nodeId, data) => {
        const ratio = currentSigma?.getCamera().ratio ?? 1;
        const frame = computeNodeFrameAttributes(data.data, { cameraRatio: ratio, degree: graph.degree(nodeId) });
        return { ...data, ...frame, x: data.x ?? 0, y: data.y ?? 0, type: "glass-node" };
      },
      edgeReducer: (_edgeId, data) => {
        const ratio = currentSigma?.getCamera().ratio ?? 1;
        const attrs = computeEdgeAttributes(data.data, {
          cameraRatio: ratio,
          strengthFilterFloor: 0,
          onPath: data.onPath ?? false,
        });
        return { ...data, ...attrs, type: "glass-edge" };
      },
      hideEdgesOnMove: true, // §1.1: "buys the frame budget at 250,000 edges"
      renderLabels: true,
      labelRenderedSizeThreshold: 0,
      enableEdgeEvents: true, // needed for edge inspection (hover/click)
    });
    currentSigma = sigma;
    sigmaRef.current = sigma;

    sigma.on("clickNode", ({ node, event }) => {
      const multi = event.original instanceof MouseEvent && (event.original.metaKey || event.original.ctrlKey);
      setSelected((prev) => {
        const next = multi ? new Set(prev) : new Set<string>();
        if (next.has(node) && multi) next.delete(node);
        else next.add(node);
        onSelectionChange?.(Array.from(next));
        return next;
      });
      setFocused(node);
      setInspectedEdge(null);
    });
    sigma.on("clickStage", () => {
      setSelected(new Set());
      onSelectionChange?.([]);
    });
    sigma.on("enterNode", ({ node }) => setHovered(node));
    sigma.on("leaveNode", () => setHovered(null));
    sigma.on("rightClickNode", ({ node, event }) => {
      event.preventSigmaDefault();
      const original = event.original as MouseEvent;
      setFocused(node);
      setRadialMenu({ x: original.clientX, y: original.clientY, nodeId: node, layout: "radial" });
    });
    sigma.on("clickEdge", ({ edge, event }) => {
      const original = event.original as MouseEvent;
      setInspectedEdge({ edgeId: edge, x: original.clientX, y: original.clientY });
    });
    sigma.on("enterEdge", ({ edge, event }) => {
      const original = event.original as MouseEvent;
      setInspectedEdge({ edgeId: edge, x: original.clientX, y: original.clientY });
    });

    return () => {
      sigma.kill();
      sigmaRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  useImperativeHandle(
    ref,
    () => ({
      focusOnNode: (nodeId: string) => {
        if (!graph.hasNode(nodeId)) return;
        setSelected(new Set([nodeId]));
        onSelectionChange?.([nodeId]);
        setFocused(nodeId);
        const sigma = sigmaRef.current;
        if (!sigma) return;
        const x = graph.getNodeAttribute(nodeId, "x") ?? 0;
        const y = graph.getNodeAttribute(nodeId, "y") ?? 0;
        // Pan only — the current zoom ratio is left untouched (`camera.animate` merges the given
        // keys, per Sigma's own `CameraState` semantics), so "centre" means exactly that and
        // nothing else, the simplest deterministic behaviour to both implement and assert against
        // in `keyboard/metrics-panel.spec.ts`.
        sigma.getCamera().animate({ x, y }, { duration: 200 });
      },
    }),
    [graph, onSelectionChange],
  );

  // Keyboard: accessibility floor (`docs/02_GLASS_FRONTEND.md` §6) — every
  // canvas action reachable without a mouse.
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    // `RadialMenu` is rendered as this container's own child, so a keydown on
    // one of its `<button role="menuitem">` items bubbles up to this same
    // handler (React's synthetic events follow real DOM bubbling). Found
    // while wiring B11's own keyboard test: without this guard, Tab inside
    // an open menu was *also* being caught by the ring-cycling branch below,
    // which calls `preventDefault()` and fights the browser's native
    // button-to-button focus movement the menu's own real `<button>`
    // elements otherwise get for free. `Escape` still closes the menu
    // regardless — that is `RadialMenu`'s own `document`-level listener, not
    // this handler, so it needs no exemption here.
    //
    // Phase 6a Stage 4: `inspectedEdge`/`clusterExplain` get the same exemption, found the same
    // way — without it, this container's own Tab/arrow branches below fight a keyboard-only
    // analyst trying to reach either overlay's own close button, the identical bug class
    // `radialMenu` was already exempted from. `Escape` needs no branch here: `Popover` (the base
    // both overlays render through) now closes itself on Escape via its own `document`-level
    // listener, the same self-contained shape `RadialMenu` already had — found necessary, not
    // just tidier, because this container's own handler only runs while the container itself has
    // focus, and both overlays are opened from a radial-menu item whose own unmount drops focus to
    // `<body>`, past this div entirely.
    if (radialMenu) return;
    // `pathResult` (Phase 7 Stage 5) gets the identical exemption `inspectedEdge`/`clusterExplain`
    // already have, for the identical reason — `PathfinderOverlay` renders through the same
    // `Popover`, opened from the same radial-menu-item shape.
    if (inspectedEdge || clusterExplain || pathResult || pathError) return;
    // Tab/Shift+Tab are deliberately never intercepted here — `02_GLASS_FRONTEND.md` §6's own
    // Tab-cycling wording was corrected in Phase 7 Stage 4 (found while wiring a second
    // keyboard-driven surface beside this canvas, `07_BUILD_PLAN.md`'s own gaps entry has the
    // full incident): a container that calls `preventDefault()` on every Tab keydown once it
    // holds focus traps a keyboard user inside it for the container's own lifetime, with no way
    // to reach a sibling panel at all. Tab now behaves exactly like every other control on the
    // page — establishing the first ring happens on this container's own `onFocus` below, not on
    // a keypress after arriving; cycling an already-built ring (needed for a lasso-selected set
    // of non-adjacent nodes arrow-walk cannot reach) moves to `Ctrl`/`Cmd`+`ArrowRight`/`Left`,
    // the key Tab's release frees up for it.
    if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && (e.ctrlKey || e.metaKey) && selected.size > 0) {
      e.preventDefault();
      const ring = Array.from(selected);
      const currentIndex = focused ? ring.indexOf(focused) : -1;
      const nextIndex = e.key === "ArrowLeft"
        ? (currentIndex - 1 + ring.length) % ring.length
        : (currentIndex + 1) % ring.length;
      setFocused(ring[nextIndex] ?? null);
    } else if ((e.key === "ArrowRight" || e.key === "ArrowDown") && focused) {
      const neighbours = graph.neighbors(focused);
      if (neighbours.length > 0) setFocused(neighbours[0] ?? null);
    } else if ((e.key === "ArrowLeft" || e.key === "ArrowUp") && focused) {
      const neighbours = graph.neighbors(focused);
      if (neighbours.length > 0) setFocused(neighbours[neighbours.length - 1] ?? null);
    } else if (e.key === " " && focused) {
      // `02_GLASS_FRONTEND.md` §6 names Tab/Arrow/Enter/`\` and is silent on
      // building a multi-node selection by keyboard at all — Space toggling
      // the focused node's own ring membership is this build's own
      // resolution of that silence (proposed, not spec-mandated), mirroring
      // `clickNode`'s own ctrl/cmd-click toggle below exactly. B11 (manual
      // link/split) is the first feature that needs a keyboard-built
      // two-node selection; nothing before it did.
      e.preventDefault();
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(focused)) next.delete(focused);
        else next.add(focused);
        onSelectionChange?.(Array.from(next));
        return next;
      });
    } else if (e.key === "Enter" && focused) {
      void expandNode(focused, null);
    } else if (e.key === "\\" && focused) {
      e.preventDefault();
      const rect = containerRef.current?.getBoundingClientRect();
      setRadialMenu({
        x: (rect?.left ?? 0) + 40,
        y: (rect?.top ?? 0) + 40,
        nodeId: focused,
        layout: "list",
      });
    }
  };

  async function expandNode(nodeId: string, edgeType: string | null): Promise<void> {
    const response = await fetch(`${apiBaseUrl}/v1/investigations/${investigationId}/expand`, {
      method: "POST",
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        request: {
          node_ids: [nodeId],
          depth: 1,
          edge_types: edgeType ? [edgeType] : null,
        },
      }),
    });
    if (!response.ok) return; // limit_exceeded (409) surfaces via a Toast at the App layer, not here
    const outcome = await response.json();
    store.getState().applyDelta(outcome.delta);
  }

  // `08_ACCEPTANCE_SCENARIOS.md` B11 / `07_BUILD_PLAN.md` Phase 6a Stage 1: "a SAME_AS with
  // score 1.0, provenance asserted, attributed to the analyst" — attribution needs no plumbing
  // here beyond the same `bearerToken` `expandNode` already sends, since `link_resolution_route`/
  // `split_resolution_route` (`services/api/app.py`) resolve the writing principal from that same
  // bearer token's own `PrincipalDep`, never a service identity. Both routes return the same
  // `DeltaReproject` shape `set_resolution_threshold` already does, so `applyDelta` needs no new
  // handling for it. `node_a`/`node_b` are sent flat, not wrapped in `{request: ...}` the way
  // `/expand`'s own `ExpandBody` is — `ManualAssertionRequest` (`services/api/resolution.py`) is
  // the whole body, checked directly rather than assumed from `expandNode`'s own different shape.
  async function manualAssertion(nodeA: string, nodeB: string, kind: "link" | "split"): Promise<void> {
    const response = await fetch(
      `${apiBaseUrl}/v1/investigations/${investigationId}/resolution/${kind}`,
      {
        method: "POST",
        headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ node_a: nodeA, node_b: nodeB }),
      },
    );
    if (!response.ok) return; // surfaces via a Toast at the App layer, not here — same as expandNode
    const delta = await response.json();
    store.getState().applyDelta(delta);
  }

  // `08_ACCEPTANCE_SCENARIOS.md` B10 / `07_BUILD_PLAN.md` Phase 6a Stage 3: "per-comparison match
  // weights, not just the total." A `GET`, unlike `expandNode`/`manualAssertion` — `explain_cluster`
  // is a pure read of the working set's own last-computed clustering, nothing to attribute to this
  // principal beyond the bearer token every other read here already sends.
  async function explainCluster(clusterId: string, x: number, y: number): Promise<void> {
    const response = await fetch(
      `${apiBaseUrl}/v1/investigations/${investigationId}/resolution/explain/${clusterId}`,
      { headers: { Authorization: `Bearer ${bearerToken}` } },
    );
    if (!response.ok) return; // a stale cluster id 404s (`ClusterNotFoundError`) — nothing to show
    const explanation: ClusterExplanation = await response.json();
    setClusterExplain({ x, y, explanation });
  }

  // Phase 7 Stage 5 (the pathfinder) — `06_DECISIONS.md` ADR-033. `POST /v1/paths` is a bare,
  // non-investigation-scoped query (the same reasoning `/v1/search` already has: it searches the
  // whole access-filtered corpus, not this investigation's own working set), so the result must be
  // seeded into this working set before it can be drawn on-path at all — reusing the existing
  // `/seed` endpoint exactly, not a new working-set-service method. Only nodes/edges not already
  // present are sent; `/seed` itself is idempotent-by-id on the store side regardless.
  async function findPaths(nodeA: string, nodeB: string, x: number, y: number): Promise<void> {
    let response: Response;
    try {
      response = await fetch(`${apiBaseUrl}/v1/paths`, {
        method: "POST",
        headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ source: nodeA, target: nodeB, max_hops: 6, k: 5 }),
      });
      if (!response.ok) {
        throw new Error(`Path search failed (${response.status}). Try again.`);
      }
    } catch (err) {
      // Not "No path found" (`pathResult`'s own zero-length case, a completed search) — the
      // search did not complete at all, and folding the two together would tell the analyst
      // something the system does not actually know (`06_DECISIONS.md` ADR-033's own "FIRST"
      // reasoning: this searches the whole access-filtered corpus, a real claim worth getting
      // right). Matches `patterns/api.ts`'s own `throw` shape, not `if (!response.ok) return;`.
      setPathError({ x, y, message: err instanceof Error ? err.message : String(err) });
      return;
    }
    const found: GraphPath[] = await response.json();

    if (found.length > 0) {
      const nodesById = new Map<string, Node>();
      const edgesById = new Map<string, Edge>();
      for (const path of found) {
        for (const n of path.nodes) nodesById.set(n.id, n);
        for (const e of path.edges) edgesById.set(e.id, e);
      }
      const newNodes = [...nodesById.values()].filter((n) => !graph.hasNode(n.id));
      const newEdges = [...edgesById.values()].filter((e) => !graph.hasEdge(e.id));
      if (newNodes.length > 0 || newEdges.length > 0) {
        const seedResponse = await fetch(
          `${apiBaseUrl}/v1/investigations/${investigationId}/seed`,
          {
            method: "POST",
            headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
            body: JSON.stringify({ nodes: newNodes, edges: newEdges }),
          },
        );
        if (seedResponse.ok) {
          const outcome = await seedResponse.json();
          store.getState().applyDelta(outcome.delta);
        }
      }
    }

    setPathResult({ x, y, paths: found, activeIndex: 0 });
  }

  function cyclePathfinderResult(direction: 1 | -1): void {
    setPathResult((prev) => {
      if (!prev || prev.paths.length <= 1) return prev;
      const nextIndex = (prev.activeIndex + direction + prev.paths.length) % prev.paths.length;
      return { ...prev, activeIndex: nextIndex };
    });
  }

  function dismissPathfinderResult(): void {
    setPathResult(null);
  }

  function dismissPathError(): void {
    setPathError(null);
  }

  function radialMenuItems(nodeId: string): RadialMenuItem[] {
    if (!graph.hasNode(nodeId)) return [];
    const node = graph.getNodeAttribute(nodeId, "data");
    const valid = edgeTypes.filter(
      (et) => et.from.includes(node.type) || et.to.includes(node.type),
    );
    const items = valid.map((et) => ({
      id: et.name,
      label: et.name,
      count: 0, // populated by expand/preview in a follow-up pass, not blocking the action itself
      onSelect: () => void expandNode(nodeId, et.name),
    }));

    // B11: only offered on a *pair* — `selected` (the ring, closed over from this component's own
    // state) is what tells the menu a second node exists, since the menu is always opened on one
    // `nodeId` (a right-click or `\`), never on a pair directly.
    if (selected.size === 2 && selected.has(nodeId)) {
      const other = Array.from(selected).find((id) => id !== nodeId);
      if (other) {
        items.push(
          {
            id: "manual-link",
            label: `Link to ${other}`,
            count: 0,
            onSelect: () => void manualAssertion(nodeId, other, "link"),
          },
          {
            id: "manual-split",
            label: `Split from ${other}`,
            count: 0,
            onSelect: () => void manualAssertion(nodeId, other, "split"),
          },
          {
            // Phase 7 Stage 5 — the same pair-selection shape B11 above already established,
            // reused rather than a new selection mechanism invented for it.
            id: "find-paths",
            label: `Find paths to ${other}`,
            count: 0,
            onSelect: () => {
              const anchor = radialMenu ?? { x: 0, y: 0 };
              void findPaths(nodeId, other, anchor.x, anchor.y);
            },
          },
        );
      }
    }

    // B10: single-node trigger, unlike B11's pair requirement — `explain` takes one `cluster_id`,
    // not two node ids. Only offered when the cluster actually has more than one current member
    // (the same `resolution.cluster_id` accessor `refreshClusterVisualState` already uses) —
    // a singleton's own "cluster" is itself, nothing to explain about how it got there.
    const clusterId = node.resolution?.cluster_id;
    if (clusterId) {
      let clusterSize = 0;
      graph.forEachNode((otherId, attrs) => {
        if ((attrs.data.resolution?.cluster_id ?? otherId) === clusterId) clusterSize += 1;
      });
      if (clusterSize > 1) {
        items.push({
          id: "explain-cluster",
          label: "Explain cluster",
          count: 0,
          onSelect: () => {
            const anchor = radialMenu ?? { x: 0, y: 0 };
            void explainCluster(clusterId, anchor.x, anchor.y);
          },
        });
      }
    }

    // B6: single-node trigger, `Endpoint`-type only — `08_ACCEPTANCE_SCENARIOS.md`'s own wording
    // ("the shared endpoint's messages") is specific about the node type, not generalised to every
    // node here. Owns no Dossier state itself; `App.tsx` does, the same split `onSelectionChange`
    // already establishes.
    if (node.type === "Endpoint" && onViewMessages) {
      items.push({
        id: "view-messages",
        label: "View messages",
        count: 0,
        onSelect: () => void onViewMessages(nodeId),
      });
    }

    return items;
  }

  return (
    <div
      ref={containerRef}
      role="application"
      aria-label="Network canvas"
      tabIndex={0}
      onKeyDown={onKeyDown}
      onFocus={(e) => {
        // The keyboard-only entry point, moved off Tab's own keydown (see `onKeyDown`'s own
        // comment on why) — reaching this container by any means (Tab, a click, `.focus()`)
        // with no ring yet establishes a one-node ring immediately, so every subsequent
        // documented behaviour (arrows, Enter, `\`) has something to act on without needing an
        // extra keypress first. `e.target === e.currentTarget` matters: React's own `onFocus`
        // bubbles (via `focusin`), so without this guard, focus landing on a *descendant* — the
        // lasso toggle button, a radial-menu item — would also fire this and re-establish a ring
        // an analyst may have deliberately built past a single node already.
        if (e.target !== e.currentTarget || selected.size > 0) return;
        const first = graph.nodes()[0];
        if (!first) return;
        setSelected(new Set([first]));
        setFocused(first);
        onSelectionChange?.([first]);
      }}
      style={{ width: "100%", height: "100%", position: "relative", outline: "none" }}
      onPointerDown={(e) => {
        if (!lassoActive) return;
        setLassoPoints([{ x: e.clientX, y: e.clientY }]);
      }}
      onPointerMove={(e) => {
        if (!lassoActive || lassoPoints.length === 0) return;
        setLassoPoints((prev) => [...prev, { x: e.clientX, y: e.clientY }]);
      }}
      onPointerUp={() => {
        if (!lassoActive || lassoPoints.length < 3) {
          setLassoPoints([]);
          return;
        }
        const sigma = sigmaRef.current;
        if (!sigma) return;
        const containerRect = containerRef.current!.getBoundingClientRect();
        const polygon = lassoPoints.map((p) => ({ x: p.x - containerRect.left, y: p.y - containerRect.top }));
        const inside = new Set<string>();
        graph.forEachNode((nodeId, attrs) => {
          const viewport = sigma.graphToViewport({ x: attrs.x ?? 0, y: attrs.y ?? 0 });
          if (pointInPolygon(viewport, polygon)) inside.add(nodeId);
        });
        setSelected(inside);
        onSelectionChange?.(Array.from(inside));
        setLassoPoints([]);
      }}
    >
      <button
        type="button"
        className="icon-btn"
        aria-pressed={lassoActive}
        title="Lasso select"
        style={{ position: "absolute", top: 8, left: 8, zIndex: 10 }}
        onClick={() => setLassoActive((v) => !v)}
      >
        ⬚
      </button>
      {lassoActive && lassoPoints.length > 1 && (
        <svg style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 9 }}>
          <polyline
            points={lassoPoints.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="rgba(192,138,52,0.15)"
            stroke="var(--brass)"
            strokeWidth={1.5}
            strokeDasharray="4 2"
          />
        </svg>
      )}
      {radialMenu && (
        <RadialMenu
          x={radialMenu.x}
          y={radialMenu.y}
          layout={radialMenu.layout}
          items={radialMenuItems(radialMenu.nodeId)}
          onClose={() => setRadialMenu(null)}
        />
      )}
      {inspectedEdge && graph.hasEdge(inspectedEdge.edgeId) && (
        <EdgeInspectionOverlay
          x={inspectedEdge.x}
          y={inspectedEdge.y}
          edge={graph.getEdgeAttribute(inspectedEdge.edgeId, "data")}
          onClose={() => setInspectedEdge(null)}
        />
      )}
      {clusterExplain && (
        <ClusterExplainOverlay
          x={clusterExplain.x}
          y={clusterExplain.y}
          explanation={clusterExplain.explanation}
          graph={graph}
          onClose={() => setClusterExplain(null)}
        />
      )}
      {communityHulls && communityHulls.size > 0 && (
        <CommunityHullOverlay sigmaRef={sigmaRef} hulls={communityHulls} />
      )}
      {pathResult && (
        <PathfinderOverlay
          x={pathResult.x}
          y={pathResult.y}
          paths={pathResult.paths}
          activeIndex={pathResult.activeIndex}
          onCycle={cyclePathfinderResult}
          onClose={dismissPathfinderResult}
        />
      )}
      {pathError && (
        <PathfinderErrorOverlay
          x={pathError.x}
          y={pathError.y}
          message={pathError.message}
          onClose={dismissPathError}
        />
      )}
    </div>
  );
});

