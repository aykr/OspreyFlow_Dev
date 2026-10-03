// The Sigma-bound canvas — `spec/02_GLASS_FRONTEND.md` §1/§1.1,
// This checkpoint's own plan: "Sigma renderer with the
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
// - Edges render as straight lines (`EdgeLineProgram`), with an arrowhead
//   (`EdgeArrowProgram`) only for an edge type the ontology declares directed.
//   `@sigma/edge-curve`'s curved-parallel-edges at the Neighbourhood/
//   Link-detail bands (§1.1's table) is installed but not yet wired — a
//   visual refinement, not a correctness requirement this phase's exit
//   criterion tests.
// - A node is first placed by a deterministic pseudo-random scatter; a
//   force layout (`forceLayout.ts`, repulsion plus edge attraction) then
//   settles the working set whenever nodes or edges are added, for up to
//   `FORCE_LAYOUT_MAX_NODES` nodes. It is not ForceAtlas2 in a worker
//   (§5's own technique for the 50k/250k fixture), which is still not built
//   and still unmeasured; past the cap the scatter stays as it is.
import { createNodeBorderProgram } from "@sigma/node-border";
import { createNodeImageProgram } from "@sigma/node-image";
import type { StoreApi } from "zustand/vanilla";
import { useStore } from "zustand/react";
import {
  EdgeArrowProgram,
  EdgeLineProgram,
  createNodeCompoundProgram,
} from "sigma/rendering";
import { animateNodes } from "sigma/utils";
import Sigma from "sigma";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  Edge,
  EdgeTypeDef,
  Node,
  Path as GraphPath,
} from "../../../../packages/schemas/generated";
import type { ExportMark } from "../export/api";
import { captureChartImage } from "../export/chartExport";
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
  nodeLabel,
  computeNodeGraphAttributes,
  edgeProgramFor,
} from "./nodeAttributes";
import {
  RadialMenu,
  type RadialMenuItem,
} from "../design/primitives/RadialMenu";
import { redrawWhenCameraStops } from "./cameraMoves";
import { edgeTypesOfferedFor } from "./edgeTypeMenu";
import {
  gateExpansion,
  narrowingOptions,
  type NarrowingOption,
} from "./expansionGate";
import { fetchWouldAdd } from "./expansionPreview";
import { LargeExpansionPrompt } from "./LargeExpansionPrompt";
import { removeFromWorkingSet } from "./removeNodes";
import { ViewActions } from "./ViewActions";
import { settleLayout, type LayoutNode } from "./forceLayout";
import { arrange, type LayoutMode } from "./layoutModes";
import { LayoutMenu } from "./LayoutMenu";
import { CommunitiesControls } from "./CommunitiesControls";
import { CommunityBoxOverlay } from "./CommunityBoxOverlay";
import { JudgementBadgeOverlay } from "./JudgementBadgeOverlay";
import { activePalette } from "../color/palette";
import { onThemeChange } from "../theme/theme";
import {
  boxAt,
  collapseView,
  communityBoxes,
  findCommunities,
  reconcileCollapsed,
  type Box,
  type CollapsedView,
} from "./communities";
import {
  expandOnDoubleClick,
  menuRequestForRightClick,
  previewCountFrom,
  type PreviewCount,
} from "./nodeGestures";
import { nearestEdge, nextLink, type ScreenSegment } from "./edgeSelection";
import { ClusterExplainOverlay } from "./ClusterExplainOverlay";
import { CommunityHullOverlay } from "./CommunityHullOverlay";
import { PathfinderOverlay } from "./PathfinderOverlay";
import { PathfinderErrorOverlay } from "./PathfinderErrorOverlay";
import { ActionErrorOverlay } from "./ActionErrorOverlay";
import type { ClusterExplanation } from "../workingset/models";

const NODE_PROGRAM = createNodeCompoundProgram<
  WorkingSetNodeAttributes,
  WorkingSetEdgeAttributes
>([
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
        size: {
          attribute: "clusterBorderSize",
          defaultValue: 0,
          mode: "pixels",
        },
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
  for (let i = 0; i < nodeId.length; i++)
    hash = (hash * 31 + nodeId.charCodeAt(i)) | 0;
  const angle = (((hash >>> 0) % 3600) / 3600) * 2 * Math.PI;
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
   * dimmed, never removed, per `spec/02_GLASS_FRONTEND.md` §2 rule 2.
   * Defaults to an empty set so this prop stays optional for any caller
   * that hasn't wired cross-filtering (e.g. an existing test harness). */
  dimmedNodeIds?: ReadonlySet<string>;
  onSelectionChange?: (nodeIds: string[]) => void;
  /** The link now selected, or `null` when none is. Selecting a link clears the node selection,
   * and selecting a node clears the link, so the Inspector shows one thing at a time. */
  onEdgeSelect?: (edge: Edge | null) => void;
  /** The keyboard-focused node id (`spec/02_GLASS_FRONTEND.md` §6: "Tab
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
  /** ADR-066: how many nodes are now folded into Group Nodes (the stand-ins included), so the
   * status bar can say so. Zero when nothing is folded. */
  onGroupedCountChange?: (count: number) => void;
  /** ADR-070: how many judgements rest on each node, drawn as a small count beside it. Omitted or
   * empty, nothing is drawn. */
  judgementCounts?: ReadonlyMap<string, number>;
}

/** Phase 7 Stage 3: what the metrics panel needs from outside the canvas's own event handlers —
 * "row-select-and-centre" is real application logic (a camera pan, not merely a browser default),
 * so it is proven end-to-end by `keyboard/metrics-panel.spec.ts`. */
export interface GlassCanvasHandle {
  /** Selects `nodeId` (firing `onSelectionChange`/`onFocusChange` exactly as a mouse click would)
   * and pans the camera to centre it, without changing the current zoom ratio — a no-op if
   * `nodeId` is not in `graph` (e.g. a stale metrics-panel row after a working-set change). */
  focusOnNode: (nodeId: string) => void;
  /** Phase 8 Stage 4c: the Judgements tab's own bidirectional evidence highlighting
   * (`02_GLASS_FRONTEND.md` §9.2). **A disclosed simplification against §9.2's own original text**
   * ("reusing the existing 8% channel opacity overlay convention") — that convention is a
   * per-*region* hull polygon (`communityHulls`, above) or a per-*text-span* background
   * (`dossier/HighlightedMessage.tsx`), neither of which has a per-*node* shape; building one
   * would mean a new WebGL node-program visual channel, real rendering-engine work `07_
   * BUILD_PLAN.md`'s own Stage 4c entry discloses as out of this stage's own scope. Reuses the
   * *selected* state instead (already a first-class, real multi-node state this canvas supports
   * via lasso) — every id in `nodeIds` that exists in `graph` is selected together; ids that do
   * not exist (a citation to a node not in the current working set) are silently skipped, not an
   * error, since evidence can legitimately live outside the working set the canvas currently
   * renders. No camera pan — unlike `focusOnNode`, a multi-node "fit view to selection" is its
   * own real feature this method does not attempt. */
  highlightNodes: (nodeIds: readonly string[]) => void;
  /** Where `nodeId` is drawn now, in pixels from the canvas's top-left corner, or `null` if it is
   * not in `graph` or nothing is mounted. Lets a browser test click on or beside a link without
   * guessing where the layout put it. */
  viewportPositionOf: (nodeId: string) => { x: number; y: number } | null;
  /** The name the canvas draws beside `nodeId` right now (empty when it draws none), or `null` if
   * the node is not in `graph` or nothing is mounted. Labels are painted to a canvas, so a browser
   * test cannot read them from the page; this asks the renderer what it was given. */
  labelOf: (nodeId: string) => string | null;
  /** Draws `nodeId` and everything within `depth` links of it, counted first and asked about when
   * large, exactly as a double-click expansion is (ADR-070: choosing a search result draws three
   * steps out). A no-op if `nodeId` is not in the view. */
  expandFrom: (nodeId: string, depth: number) => void;
  /** Phase 8 Stage 4h: the chart artefact's own real capture path
   * (`02_GLASS_FRONTEND.md` §10.1/§10.3) — delegates to `captureChartImage`
   * (`export/chartExport.ts`), which renders the live Sigma instance to a PNG via
   * `@sigma/export-image`, composites the visible watermark, and embeds the mark's own fields
   * as machine-readable `tEXt` chunks. Rejects if no Sigma instance is mounted yet (the same
   * "no-op/rejects on an unready renderer" shape `focusOnNode`'s own `graph.hasNode` guard
   * already establishes, made a rejection rather than a silent no-op here because a caller
   * that requested a download needs to know it did not get one). */
  exportImage: (mark: ExportMark) => Promise<Blob>;
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

/** The selected link: the brass the lasso already uses. */

export const GlassCanvas = forwardRef<GlassCanvasHandle, GlassCanvasProps>(
  function GlassCanvas(
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
      onEdgeSelect,
      onFocusChange,
      onViewMessages,
      communityHulls,
      onGroupedCountChange,
      judgementCounts,
    }: GlassCanvasProps,
    ref,
  ) {
    const containerRef = useRef<HTMLDivElement>(null);
    const sigmaRef = useRef<Sigma<
      WorkingSetNodeAttributes,
      WorkingSetEdgeAttributes
    > | null>(null);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [hovered, setHovered] = useState<string | null>(null);
    const [focused, setFocused] = useState<string | null>(null);
    useEffect(() => {
      onFocusChange?.(focused);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [focused]);
    const [radialMenu, setRadialMenu] = useState<PendingRadialMenu | null>(
      null,
    );
    // **The radial menu's real cardinality, per edge type** — `08_ACCEPTANCE_SCENARIOS.md` A1:
    // "expansion previews its cardinality before running: the analyst is never surprised by ten
    // thousand nodes". Until round 12c this was hardcoded to 0 for every entry, so the menu read
    // `ASSOCIATE_OF (0)` on a node with eight associates and `USES (0)` on one with none — the
    // same text for "nothing there" and "eight there", which is worse than showing nothing at all,
    // and it cost round 12b real time chasing an expansion that could never have worked.
    // Keyed by edge type, for the node the menu is currently open on; `null` means "not answered
    // yet", which renders as `…` rather than as a confident zero.
    // The latest `requestExpansion`, for the Sigma handlers registered once in an effect: a closure over
    // the first render's copy would expand against a stale working set.
    // Read by the Sigma reducers, which are registered once: a closure over the first render's
    // `hovered` or `edgeTypes` would never see a change.
    const hoveredRef = useRef<string | null>(null);
    const edgeTypesRef = useRef<readonly EdgeTypeDef[]>([]);
    const settledRef = useRef<Set<string>>(new Set());
    // The layout the analyst chose (organic until they choose another). A ref as well as state:
    // the layout effect below runs from graph events and must read the current choice.
    const [layoutMode, setLayoutMode] = useState<LayoutMode>("organic");
    const layoutModeRef = useRef<LayoutMode>("organic");
    const selectedRef = useRef<Set<string>>(new Set());
    selectedRef.current = selected;
    const arrangeNowRef = useRef<() => void>(() => undefined);
    const selectLinkRef = useRef<(edgeId: string | null) => void>(() => undefined);
    const requestExpansionRef = useRef<
      | ((
          nodeId: string,
          edgeType: string | null,
          x: number,
          y: number,
          depth?: number,
        ) => Promise<void>)
      | null
    >(null);
    const [previewCounts, setPreviewCounts] = useState<
      Record<string, PreviewCount | null>
    >({});
    // **Owner ruling R7 (TENTATIVE, 27 September 2026) — step one of two.** Node id -> the reason
    // it is marked for suppression. A mark suppresses nothing; it is a visible proposal, and the
    // suppression only takes effect once its evidence arrives through the Ingest Studio.
    // `02_GLASS_FRONTEND.md` §9.5.
    const [suppressionMarks, setSuppressionMarks] = useState<
      Record<string, string>
    >({});
    // A link selected by click or by keyboard. A ref as well, because the Sigma edge reducer
    // reads it when drawing.
    const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
    const selectedEdgeRef = useRef<string | null>(null);
    selectedEdgeRef.current = selectedEdge;
    // Links hidden from this view in this browser tab only (not recorded anywhere, not in History).
    const [hiddenEdges, setHiddenEdges] = useState<ReadonlySet<string>>(new Set());
    const hiddenEdgesRef = useRef<ReadonlySet<string>>(new Set());
    hiddenEdgesRef.current = hiddenEdges;
    const [clusterExplain, setClusterExplain] = useState<{
      x: number;
      y: number;
      explanation: ClusterExplanation;
    } | null>(null);
    // Phase 7 Stage 5 (the pathfinder) — `x`/`y` anchor the overlay to the radial menu's own
    // position, the same shape `clusterExplain` above already uses. `activeIndex` is which of the
    // (up to `k`) found paths is currently drawn on-path; cycling it never re-fetches.
    const [pathResult, setPathResult] = useState<{
      x: number;
      y: number;
      paths: GraphPath[];
      activeIndex: number;
    } | null>(null);
    // A failed `/v1/paths` call — distinguishable from `pathResult`'s own "No path found" (a
    // completed search, zero results) rather than folded into it, since the two are different
    // findings for the analyst (`findPaths`'s own doc comment below has the full reasoning).
    const [pathError, setPathError] = useState<{
      x: number;
      y: number;
      message: string;
    } | null>(null);
    // An expansion that would add more nodes than `EXPANSION_CONFIRM_ABOVE` (or whose size could
    // not be counted) waits here for the analyst's choice; nothing is added until they make it.
    const [pendingExpansion, setPendingExpansion] = useState<{
      nodeId: string;
      edgeType: string | null;
      x: number;
      y: number;
      wouldAdd: number | "unavailable";
      options: NarrowingOption[];
      depth: number;
    } | null>(null);
    // A failed `expandNode`/`manualAssertion`/`explainCluster` call — `ActionErrorOverlay`'s own
    // doc comment has the full reasoning for why these three share one generic overlay rather than
    // `pathError`'s own distinct-outcomes shape.
    const [actionError, setActionError] = useState<{
      x: number;
      y: number;
      message: string;
    } | null>(null);
    // Read by `refreshNodeVisualState` (called from many unrelated call sites — hover, selection,
    // dimming) without threading a new parameter through every one of them; written only by the
    // effect below, keyed on `pathResult` itself. A ref, not state, because nothing here needs a
    // re-render when it changes on its own — the effect that writes it already re-renders via
    // `pathResult`.
    const pathNodeIdsRef = useRef<Set<string>>(new Set());
    const [lassoActive, setLassoActive] = useState(false);
    const [lassoPoints, setLassoPoints] = useState<{ x: number; y: number }[]>(
      [],
    );
    const lastReproject = useStore(store, (s) => s.lastReproject);
    // Re-render when the working set changes, so the view's node count stays current.
    const workingSetSeq = useStore(store, (s) => s.seq);

    // **Communities (ADR-066).** A way of looking at the nodes now in view: groups of closely linked
    // nodes get a box, and a group can be folded into one Group Node and opened again. Nothing here
    // is stored or sent to the server, and switching it off puts every node back as it was.
    const [communitiesOn, setCommunitiesOn] = useState(false);
    const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
    const communities = useMemo(
      () =>
        communitiesOn
          ? findCommunities(
              graph.nodes(),
              graph.edges().map((e) => [graph.source(e), graph.target(e)] as const),
            )
          : [],
      // `workingSetSeq` changes whenever nodes or links are added or removed.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [communitiesOn, graph, workingSetSeq],
    );
    const communitiesRef = useRef(communities);
    communitiesRef.current = communities;
    const collapsedRef = useRef(collapsed);
    collapsedRef.current = collapsed;
    const communitiesOnRef = useRef(false);
    communitiesOnRef.current = communitiesOn;
    // What is folded right now, worked out from where the nodes are drawn. Read by the Sigma
    // reducers, which are registered once.
    const foldedViewRef = useRef<CollapsedView | null>(null);
    const recomputeFoldRef = useRef<() => void>(() => undefined);
    const foldGroupRef = useRef<(communityId: string) => void>(() => undefined);
    const unfoldGroupRef = useRef<(communityId: string) => void>(() => undefined);
    const isHiddenInGroup = (nodeId: string): boolean =>
      foldedViewRef.current?.hidden.has(nodeId) ?? false;
    const currentBoxesRef = useRef<() => Box[]>(() => []);

    // Sigma reads every node's position from the graph on each draw and ignores a position a
    // reducer returns (checked in its source: `process` copies `x` and `y` from the graph's own
    // attributes). So a folded group is drawn at its centre by really moving its members' stored
    // positions there, and remembering where they were: `realPositionsRef` holds where each folded
    // member truly is, `drawnPositionsRef` where it was put, so a layout or a drag that writes a new
    // position afterwards is noticed (the stored position no longer matches what was put there).
    const realPositionsRef = useRef(new Map<string, { x: number; y: number }>());
    const drawnPositionsRef = useRef(new Map<string, { x: number; y: number }>());

    /** Where a node really is, whether or not its group is folded. */
    function realPositionOf(id: string): { x: number; y: number } {
      return (
        realPositionsRef.current.get(id) ?? {
          x: graph.getNodeAttribute(id, "x") ?? 0,
          y: graph.getNodeAttribute(id, "y") ?? 0,
        }
      );
    }

    /** Where the nodes of the given groups really are (their layout positions). */
    function positionsOf(groups: readonly { members: readonly string[] }[]): Map<string, { x: number; y: number }> {
      const positions = new Map<string, { x: number; y: number }>();
      for (const group of groups) {
        for (const id of group.members) {
          if (!graph.hasNode(id)) continue;
          positions.set(id, realPositionOf(id));
        }
      }
      return positions;
    }

    // The boxes to draw: one per group that is not folded, kept a fixed distance (in pixels) clear
    // of the nodes inside whatever the zoom.
    currentBoxesRef.current = (): Box[] => {
      if (!communitiesOn) return [];
      const sigma = sigmaRef.current;
      const open = communities.filter((c) => !collapsed.has(c.id));
      if (!sigma || open.length === 0) return [];
      const origin = sigma.graphToViewport({ x: 0, y: 0 });
      const unit = sigma.graphToViewport({ x: 1, y: 0 });
      const pixelsPerUnit = Math.hypot(unit.x - origin.x, unit.y - origin.y) || 1;
      return communityBoxes(open, positionsOf(open), 16 / pixelsPerUnit);
    };

    recomputeFoldRef.current = () => {
      const real = realPositionsRef.current;
      const drawn = drawnPositionsRef.current;
      const place = (id: string, at: { x: number; y: number }) => {
        if (graph.getNodeAttribute(id, "x") !== at.x || graph.getNodeAttribute(id, "y") !== at.y) {
          graph.mergeNodeAttributes(id, { x: at.x, y: at.y });
        }
      };
      // A folded member whose stored position is no longer where it was put has been moved (a layout
      // ran, or it was dragged): that is its real position now.
      for (const id of [...real.keys()]) {
        if (!graph.hasNode(id)) {
          real.delete(id);
          drawn.delete(id);
          continue;
        }
        const at = drawn.get(id);
        const x = graph.getNodeAttribute(id, "x") ?? 0;
        const y = graph.getNodeAttribute(id, "y") ?? 0;
        if (!at || at.x !== x || at.y !== y) real.set(id, { x, y });
      }
      const folded = communitiesRef.current.filter((c) => collapsedRef.current.has(c.id));
      const foldedIds = new Set(folded.flatMap((c) => c.members));
      // What is no longer folded goes back to where it really is.
      for (const [id, at] of [...real]) {
        if (foldedIds.has(id)) continue;
        place(id, at);
        real.delete(id);
        drawn.delete(id);
      }
      if (folded.length === 0) {
        foldedViewRef.current = null;
        return;
      }
      for (const id of foldedIds) {
        if (!graph.hasNode(id) || real.has(id)) continue;
        real.set(id, {
          x: graph.getNodeAttribute(id, "x") ?? 0,
          y: graph.getNodeAttribute(id, "y") ?? 0,
        });
      }
      const view = collapseView(
        communitiesRef.current,
        collapsedRef.current,
        positionsOf(folded),
        (id) => (graph.hasNode(id) ? graph.degree(id) : 0),
        (id) => (graph.hasNode(id) ? graph.getNodeAttribute(id, "data").type : ""),
      );
      foldedViewRef.current = view;
      // Every member of a folded group is drawn at its centre, so a link from outside still reaches
      // the group.
      for (const id of foldedIds) {
        if (!graph.hasNode(id)) continue;
        const centre = view.groups.get(id) ?? view.anchorOf(id);
        if (!centre) continue;
        const at = { x: centre.x, y: centre.y };
        place(id, at);
        drawn.set(id, at);
      }
    };

    const foldGroup = (communityId: string) =>
      setCollapsed((prev) => (prev.has(communityId) ? prev : new Set(prev).add(communityId)));
    const unfoldGroup = (communityId: string) =>
      setCollapsed((prev) => {
        if (!prev.has(communityId)) return prev;
        const next = new Set(prev);
        next.delete(communityId);
        return next;
      });
    foldGroupRef.current = foldGroup;
    unfoldGroupRef.current = unfoldGroup;

    // A group that no longer exists (its nodes were removed, or Communities was switched off) is
    // dropped from what is folded.
    useEffect(() => {
      setCollapsed((prev) => reconcileCollapsed(prev, communities));
    }, [communities]);

    // Whenever what is folded changes: work the view out again, tell the status bar, take nodes that
    // are no longer drawn out of the selection and the keyboard focus, and draw.
    useEffect(() => {
      recomputeFoldRef.current();
      const view = foldedViewRef.current;
      onGroupedCountChange?.(view?.groupedNodeCount ?? 0);
      if (view && view.hidden.size > 0) {
        if ([...selectedRef.current].some((id) => view.hidden.has(id))) {
          setSelected((prev) => {
            const next = new Set([...prev].filter((id) => !view.hidden.has(id)));
            onSelectionChange?.(Array.from(next));
            return next;
          });
        }
        if (focused && view.hidden.has(focused)) {
          const owner = communities.find((c) => c.members.includes(focused));
          const standIn = [...view.groups.entries()].find(([, g]) => g.communityId === owner?.id);
          setFocused(standIn ? standIn[0] : null);
        }
      }
      sigmaRef.current?.refresh();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [collapsed, communities]);

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
      const activePath = pathResult
        ? pathResult.paths[pathResult.activeIndex]
        : undefined;
      pathNodeIdsRef.current = new Set(
        activePath?.nodes.map((n) => n.id) ?? [],
      );
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
          const anchorX =
            members.length > 1
              ? graph.getNodeAttribute(clusterId, "x")
              : undefined;
          const anchorY =
            members.length > 1
              ? graph.getNodeAttribute(clusterId, "y")
              : undefined;
          if (anchorX !== undefined && anchorY !== undefined) {
            graph.mergeNodeAttributes(nodeId, { x: anchorX, y: anchorY });
          } else {
            const home = seededScatter(nodeId);
            graph.mergeNodeAttributes(nodeId, { x: home.x, y: home.y });
          }
        }
      }
    };

    // The graph is painted by WebGL, which cannot read the page's CSS variables, so a change of
    // theme (ADR-070) has to be pushed into the nodes' stored colours and the canvas drawn again.
    const redrawForThemeRef = useRef<() => void>(() => undefined);
    redrawForThemeRef.current = () => {
      const palette = activePalette();
      graph.forEachNode((nodeId, attrs) => {
        refreshNodeVisualState(nodeId);
        if ((attrs.clusterBorderSize ?? 0) > 0) {
          graph.mergeNodeAttributes(nodeId, { clusterBorderColor: palette.borderSubtle });
        }
      });
      sigmaRef.current?.refresh();
    };
    useEffect(() => onThemeChange(() => redrawForThemeRef.current()), []);

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

    // The force layout. Runs a moment after the last node or edge is added (an expansion adds many
    // at once), settles the working set and moves nodes to their new places over `--dur-graph`.
    // Cluster members share their anchor's position (`refreshClusterVisualState`), so only one
    // node per cluster takes part and the others follow it afterwards.
    useEffect(() => {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const run = () => {
        const clusterOf = (id: string) =>
          graph.getNodeAttribute(id, "data").resolution?.cluster_id ?? id;
        const nodes: LayoutNode[] = [];
        graph.forEachNode((id) => {
          if (clusterOf(id) !== id) return;
          const at = realPositionOf(id);
          nodes.push({ id, x: at.x, y: at.y });
        });
        const present = new Set(nodes.map((n) => n.id));
        const edges: [string, string][] = [];
        graph.forEachEdge((_edge, _attrs, source, target) => {
          const a = clusterOf(source);
          const b = clusterOf(target);
          if (a !== b && present.has(a) && present.has(b)) edges.push([a, b]);
        });
        // A node arriving beside an already-settled neighbour starts next to it, so an
        // expansion grows outwards from where the analyst is looking, not from a random spot.
        const positionOf = new Map(nodes.map((n) => [n.id, n]));
        for (const node of nodes) {
          if (settledRef.current.has(node.id)) continue;
          const anchor = edges
            .map(([a, b]) => (a === node.id ? b : b === node.id ? a : null))
            .find((other) => other !== null && settledRef.current.has(other));
          const at = anchor ? positionOf.get(anchor) : undefined;
          if (at) {
            const near = seededScatter(node.id);
            node.x = at.x + near.x * 0.1;
            node.y = at.y + near.y * 0.1;
          }
        }
        const mode = layoutModeRef.current;
        const settled =
          mode === "organic"
            ? settleLayout(nodes, edges)
            : arrange(
                mode,
                {
                  nodes: nodes.map((node) => ({
                    ...node,
                    type: graph.getNodeAttribute(node.id, "data").type,
                  })),
                  edges,
                },
                { centre: Array.from(selectedRef.current)[0] ?? null },
              );
        if (!settled) return; // too large to arrange quickly: the positions stay
        const targets: Record<string, { x: number; y: number }> = {};
        for (const [id, at] of settled) {
          targets[id] = at;
          settledRef.current.add(id);
        }
        animateNodes(graph, targets, { duration: 420 }, () => {
          refreshClusterVisualState();
          sigmaRef.current?.scheduleRefresh();
          const sigma = sigmaRef.current;
          if (sigma) redrawWhenCameraStops(sigma, sigma.getCamera().animatedReset({ duration: 420 }));
        });
      };
      const schedule = () => {
        clearTimeout(timer);
        timer = setTimeout(run, 150);
      };
      arrangeNowRef.current = () => {
        clearTimeout(timer);
        run();
      };
      graph.on("nodeAdded", schedule);
      graph.on("edgeAdded", schedule);
      schedule();
      return () => {
        clearTimeout(timer);
        graph.removeListener("nodeAdded", schedule);
        graph.removeListener("edgeAdded", schedule);
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [graph]);

    // Choosing a node ends the link selection, so the Inspector shows one thing at a time.
    useEffect(() => {
      if (selected.size > 0 && selectedEdge !== null) selectLinkRef.current(null);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selected]);

    // The link drawn highlighted, and the links hidden, are read by the edge reducer.
    useEffect(() => {
      sigmaRef.current?.scheduleRefresh();
    }, [selectedEdge, hiddenEdges]);

    // Re-derive graph-level visual attributes only for the node(s) whose
    // hover/selection actually changed — not the whole working set.
    useEffect(() => {
      graph.forEachNode((key) => {
        const wasSelected = selected.has(key);
        const isHovered = hovered === key;
        if (
          wasSelected ||
          isHovered ||
          graph.getNodeAttribute(key, "borderSize")
        ) {
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
      let currentSigma:
        Sigma<WorkingSetNodeAttributes, WorkingSetEdgeAttributes> | undefined;
      const sigma = new Sigma<
        WorkingSetNodeAttributes,
        WorkingSetEdgeAttributes
      >(graph, containerRef.current, {
        defaultNodeType: "glass-node",
        nodeProgramClasses: { "glass-node": NODE_PROGRAM },
        defaultEdgeType: "glass-edge",
        edgeProgramClasses: {
          "glass-edge": EdgeLineProgram,
          "glass-arrow": EdgeArrowProgram,
        },
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
          const frame = computeNodeFrameAttributes(data.data, {
            cameraRatio: ratio,
            degree: graph.degree(nodeId),
            viewNodeCount: graph.order,
            emphasised: data.emphasised === true,
          });
          const drawn = {
            ...data,
            ...frame,
            ...(data.emphasised === true ? { forceLabel: true } : {}),
            type: "glass-node",
          };
          const folded = foldedViewRef.current;
          if (!folded) return drawn;
          // A folded group is drawn as one larger, brass-ringed node labelled with what it holds.
          const group = folded.groups.get(nodeId);
          if (group) {
            return {
              ...drawn,
              size: Math.min(40, (frame.size || 6) * (1 + Math.log2(group.count) / 1.5)),
              label: group.label,
              forceLabel: true,
              borderColor: activePalette().brass,
              borderSize: 0.3,
            };
          }
          // The other members sit at the group's centre (their stored position was moved there), too
          // small to see, so a link from outside still reaches the group.
          if (folded.hidden.has(nodeId)) return { ...drawn, size: 0.1, label: "" };
          return drawn;
        },
        edgeReducer: (edgeId, data) => {
          const ratio = currentSigma?.getCamera().ratio ?? 1;
          const hoveredNode = hoveredRef.current;
          const attrs = computeEdgeAttributes(data.data, {
            cameraRatio: ratio,
            strengthFilterFloor: 0,
            onPath: data.onPath ?? false,
            viewEdgeCount: graph.size,
            touchesHoveredNode:
              hoveredNode !== null &&
              (graph.source(edgeId) === hoveredNode ||
                graph.target(edgeId) === hoveredNode),
          });
          const isSelected = edgeId === selectedEdgeRef.current;
          return {
            ...data,
            ...attrs,
            // A hidden link is not drawn; the selected one is thicker, brass, and always labelled.
            hidden:
              attrs.hidden ||
              hiddenEdgesRef.current.has(edgeId) ||
              (foldedViewRef.current?.hidesLink(graph.source(edgeId), graph.target(edgeId)) ??
                false),
            ...(isSelected
              ? {
                  size: Math.max(attrs.size * 2, 4),
                  color: activePalette().brass,
                  label: `${data.data.type} (${data.data.occurrences ?? 1})`,
                }
              : {}),
            type: edgeProgramFor(data.data.type, edgeTypesRef.current),
          };
        },
        hideEdgesOnMove: true, // §1.1: "buys the frame budget at 250,000 edges"
        renderLabels: true,
        // Edge labels were worked out (`computeEdgeAttributes`) but never drawn until this was
        // switched on. They appear only at the closest zoom, or beside the node under the pointer.
        renderEdgeLabels: true,
        labelRenderedSizeThreshold: 0,
        enableEdgeEvents: true, // needed for edge inspection (hover/click)
      });
      currentSigma = sigma;
      sigmaRef.current = sigma;

      sigma.on("clickNode", ({ node, event }) => {
        const multi =
          event.original instanceof MouseEvent &&
          (event.original.metaKey || event.original.ctrlKey);
        setSelected((prev) => {
          const next = multi ? new Set(prev) : new Set<string>();
          if (next.has(node) && multi) next.delete(node);
          else next.add(node);
          onSelectionChange?.(Array.from(next));
          return next;
        });
        setFocused(node);
      });
      sigma.on("clickStage", ({ event }) => {
        // The renderer picks a link only where its thin line is drawn, which is hard to hit. A
        // click that found neither node nor link is checked against every visible link with a
        // wider reach before it counts as a click on empty space.
        const segments: ScreenSegment[] = [];
        graph.forEachEdge((edgeId, _attrs, source, target) => {
          if (hiddenEdgesRef.current.has(edgeId)) return;
          const a = sigma.graphToViewport({
            x: graph.getNodeAttribute(source, "x") ?? 0,
            y: graph.getNodeAttribute(source, "y") ?? 0,
          });
          const b = sigma.graphToViewport({
            x: graph.getNodeAttribute(target, "x") ?? 0,
            y: graph.getNodeAttribute(target, "y") ?? 0,
          });
          segments.push({ id: edgeId, ax: a.x, ay: a.y, bx: b.x, by: b.y });
        });
        const hit = nearestEdge(event.x, event.y, segments);
        if (hit !== null) {
          selectLinkRef.current(hit);
          return;
        }
        setSelected(new Set());
        onSelectionChange?.([]);
        selectLinkRef.current(null);
      });
      sigma.on("enterNode", ({ node }) => setHovered(node));
      sigma.on("leaveNode", () => setHovered(null));
      sigma.on("rightClickNode", ({ node, event }) => {
        event.preventSigmaDefault();
        setFocused(node);
        setRadialMenu(
          menuRequestForRightClick(event.original as MouseEvent, node),
        );
      });
      // The fold is re-worked from where the nodes are just before each draw, so a folded group
      // stays at the centre of its members while the layout moves them.
      sigma.on("beforeProcess", () => recomputeFoldRef.current());
      sigma.on("doubleClickStage", ({ event }) => {
        if (!communitiesOnRef.current) return;
        const at = sigma.viewportToGraph({ x: event.x, y: event.y });
        const box = boxAt(currentBoxesRef.current(), at.x, at.y);
        if (!box) return;
        event.preventSigmaDefault();
        foldGroupRef.current(box.id);
      });
      sigma.on("doubleClickNode", ({ node, event }) => {
        const group = foldedViewRef.current?.groups.get(node);
        if (group) {
          // A Group Node opens; it does not ask the server to expand anything.
          event.preventSigmaDefault();
          unfoldGroupRef.current(group.communityId);
          return;
        }
        expandOnDoubleClick(event, node, (id, x, y) => {
          void requestExpansionRef.current?.(id, null, x, y);
        });
      });
      sigma.on("clickEdge", ({ edge }) => selectLinkRef.current(edge));

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
          redrawWhenCameraStops(sigma, sigma.getCamera().animate({ x, y }, { duration: 200 }));
        },
        highlightNodes: (nodeIds: readonly string[]) => {
          const present = nodeIds.filter((id) => graph.hasNode(id));
          setSelected(new Set(present));
          onSelectionChange?.(present);
        },
        expandFrom: (nodeId: string, depth: number) => {
          if (!graph.hasNode(nodeId)) return;
          const box = containerRef.current?.getBoundingClientRect();
          void requestExpansionRef.current?.(
            nodeId,
            null,
            (box?.width ?? 0) / 2,
            (box?.height ?? 0) / 2,
            depth,
          );
        },
        labelOf: (nodeId: string) => {
          const sigma = sigmaRef.current;
          if (!sigma || !graph.hasNode(nodeId)) return null;
          return sigma.getNodeDisplayData(nodeId)?.label ?? "";
        },
        viewportPositionOf: (nodeId: string) => {
          const sigma = sigmaRef.current;
          if (!sigma || !graph.hasNode(nodeId)) return null;
          // Where it is drawn: a folded group's members have been moved to its centre.
          const x = graph.getNodeAttribute(nodeId, "x") ?? 0;
          const y = graph.getNodeAttribute(nodeId, "y") ?? 0;
          return sigma.graphToViewport({ x, y });
        },
        exportImage: (mark: ExportMark) => {
          const sigma = sigmaRef.current;
          if (!sigma) {
            return Promise.reject(
              new Error("exportImage: no Sigma instance mounted"),
            );
          }
          return captureChartImage(sigma, mark);
        },
      }),
      [graph, onSelectionChange],
    );

    // Keyboard: accessibility floor (`spec/02_GLASS_FRONTEND.md` §6) — every
    // canvas action reachable without a mouse.
    const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
      // A key pressed on a control inside the canvas (a toolbar button, the layout menu, a box's fold
      // button) belongs to that control: React's synthetic events bubble to this container, and
      // without this guard Enter on any such button also read as "expand the focused node" and asked
      // the Conduit (found 3 October 2026; `keyboard.spec.ts` has the case). The canvas acts on keys
      // only when it is itself the focused element.
      if (e.target !== e.currentTarget) return;
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
      // Phase 6a Stage 4: `clusterExplain` gets the same exemption, found the same
      // way — without it, this container's own Tab/arrow branches below fight a keyboard-only
      // analyst trying to reach either overlay's own close button, the identical bug class
      // `radialMenu` was already exempted from. `Escape` needs no branch here: `Popover` (the base
      // both overlays render through) now closes itself on Escape via its own `document`-level
      // listener, the same self-contained shape `RadialMenu` already had — found necessary, not
      // just tidier, because this container's own handler only runs while the container itself has
      // focus, and both overlays are opened from a radial-menu item whose own unmount drops focus to
      // `<body>`, past this div entirely.
      if (radialMenu) return;
      // `pathResult` (Phase 7 Stage 5) gets the identical exemption `clusterExplain`
      // already have, for the identical reason — `PathfinderOverlay` renders through the same
      // `Popover`, opened from the same radial-menu-item shape.
      if (
        clusterExplain ||
        pathResult ||
        pathError ||
        actionError
      )
        return;
      // Tab/Shift+Tab are deliberately never intercepted here — `02_GLASS_FRONTEND.md` §6's own
      // Tab-cycling wording was corrected after being found while wiring a second
      // keyboard-driven surface beside this canvas (a disclosed gap has the
      // full incident): a container that calls `preventDefault()` on every Tab keydown once it
      // holds focus traps a keyboard user inside it for the container's own lifetime, with no way
      // to reach a sibling panel at all. Tab now behaves exactly like every other control on the
      // page — establishing the first ring happens on this container's own `onFocus` below, not on
      // a keypress after arriving; cycling an already-built ring (needed for a lasso-selected set
      // of non-adjacent nodes arrow-walk cannot reach) moves to `Ctrl`/`Cmd`+`ArrowRight`/`Left`,
      // the key Tab's release frees up for it.
      // **Walking every node in the working set, adjacency or not** — round 12d, closing a real
      // `CLAUDE.md` rule 13 gap found in 12b: `Explain cluster` and `Find paths to` are both
      // gated on a *two-node* selection, and until this branch existed there was no keyboard
      // route to one for two nodes that share no edge. Arrow-walk follows `graph.neighbors`, so
      // it cannot leave a node's own component; `Ctrl`/`Cmd`+Arrow below cycles *within* the
      // selection, so it cannot reach a node that is not already in it; Space toggles only
      // whatever is focused. Two entities found by identifier — exactly how an analyst reaches
      // Fixture Corp's resolution pair — are typically not adjacent, so both actions were
      // mouse-only in practice while appearing to be covered.
      //
      // `Shift` on top of the existing `Ctrl`/`Cmd`+Arrow, so the two ring-walks read as one
      // family: without Shift, cycle the selection; with it, cycle everything. The order is
      // `graph.nodes()`' own, which is insertion order and therefore stable within a session —
      // enough for "walk to the other one", which is all this is for.
      if (
        (e.key === "ArrowRight" || e.key === "ArrowLeft") &&
        (e.ctrlKey || e.metaKey) &&
        e.shiftKey
      ) {
        e.preventDefault();
        const all = graph.nodes().filter((id) => !isHiddenInGroup(id));
        if (all.length === 0) return;
        const currentIndex = focused ? all.indexOf(focused) : -1;
        const nextIndex =
          e.key === "ArrowLeft"
            ? (currentIndex - 1 + all.length) % all.length
            : (currentIndex + 1) % all.length;
        setFocused(all[nextIndex] ?? null);
      } else if (
        (e.key === "ArrowRight" || e.key === "ArrowLeft") &&
        (e.ctrlKey || e.metaKey) &&
        selected.size > 0
      ) {
        e.preventDefault();
        const ring = Array.from(selected).filter((id) => !isHiddenInGroup(id));
        if (ring.length === 0) return;
        const currentIndex = focused ? ring.indexOf(focused) : -1;
        const nextIndex =
          e.key === "ArrowLeft"
            ? (currentIndex - 1 + ring.length) % ring.length
            : (currentIndex + 1) % ring.length;
        setFocused(ring[nextIndex] ?? null);
      } else if ((e.key === "ArrowRight" || e.key === "ArrowDown") && focused) {
        const neighbours = graph.neighbors(focused).filter((id) => !isHiddenInGroup(id));
        if (neighbours.length > 0) setFocused(neighbours[0] ?? null);
      } else if ((e.key === "ArrowLeft" || e.key === "ArrowUp") && focused) {
        const neighbours = graph.neighbors(focused).filter((id) => !isHiddenInGroup(id));
        if (neighbours.length > 0)
          setFocused(neighbours[neighbours.length - 1] ?? null);
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
      } else if (
        (e.key === "l" || e.key === "L") &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        focused
      ) {
        // The keyboard route to a link: `L` selects the focused node's next link, `Shift+L` the
        // previous one, wrapping round. Rule 13: a link can be selected without a mouse.
        e.preventDefault();
        const next = nextLink(graph.edges(focused), selectedEdge, e.shiftKey ? -1 : 1);
        if (next !== null) selectLink(next);
      } else if (
        (e.key === "Delete" || e.key === "Backspace") &&
        selectedEdge !== null
      ) {
        e.preventDefault();
        hideSelectedLink();
      } else if (
        (e.key === "Delete" || e.key === "Backspace") &&
        selected.size > 0
      ) {
        e.preventDefault();
        void removeNodeIds(Array.from(selected));
      } else if (
        (e.key === "g" || e.key === "G") &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        focused &&
        communitiesOn
      ) {
        // The keyboard route to folding: `G` on a focused node folds its group into one node, and
        // on a Group Node opens it again (ADR-066; rule 13).
        e.preventDefault();
        const group = foldedViewRef.current?.groups.get(focused);
        if (group) {
          unfoldGroup(group.communityId);
        } else {
          const owner = communities.find((c) => c.members.includes(focused));
          if (owner) foldGroup(owner.id);
        }
      } else if (e.key === "Enter" && focused) {
        // No menu is open here to anchor on — the same container-corner-plus-offset fallback the
        // `\` handler below uses to open one, since a failed expand needs somewhere to render.
        const rect = containerRef.current?.getBoundingClientRect();
        void requestExpansion(
          focused,
          null,
          (rect?.left ?? 0) + 40,
          (rect?.top ?? 0) + 40,
        );
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

    requestExpansionRef.current = requestExpansion;
    hoveredRef.current = hovered;
    edgeTypesRef.current = edgeTypes;

    // Counts what an expansion would add before running it. Up to the limit it goes ahead; above
    // it (or when the count fails) the analyst is asked, with the count per relationship type so
    // they can narrow. Every way of expanding a node goes through here.
    async function requestExpansion(
      nodeId: string,
      edgeType: string | null,
      x: number,
      y: number,
      depth = 1,
    ): Promise<void> {
      const ask = {
        apiBaseUrl,
        bearerToken,
        investigationId,
        nodeId,
        currentOrder: graph.order,
        depth,
      };
      const total = await fetchWouldAdd(fetch, {
        ...ask,
        edgeTypes: edgeType ? [edgeType] : null,
      });
      const gate = gateExpansion(total);
      if (gate.kind === "proceed") {
        await expandNode(nodeId, edgeType, x, y, depth);
        return;
      }
      let options: NarrowingOption[] = [];
      if (edgeType === null && graph.hasNode(nodeId)) {
        const node = graph.getNodeAttribute(nodeId, "data");
        const types = edgeTypesOfferedFor(edgeTypes, node.type);
        const counts = await Promise.all(
          types.map(
            async (et) =>
              [
                et.name,
                await fetchWouldAdd(fetch, { ...ask, edgeTypes: [et.name] }),
              ] as const,
          ),
        );
        options = narrowingOptions(Object.fromEntries(counts));
      }
      setPendingExpansion({
        nodeId,
        edgeType,
        x,
        y,
        wouldAdd: gate.wouldAdd,
        options,
        depth,
      });
    }

    async function expandNode(
      nodeId: string,
      edgeType: string | null,
      x: number,
      y: number,
      depth = 1,
    ): Promise<void> {
      let response: Response;
      try {
        response = await fetch(
          `${apiBaseUrl}/v1/investigations/${investigationId}/expand`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${bearerToken}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              request: {
                node_ids: [nodeId],
                depth,
                edge_types: edgeType ? [edgeType] : null,
              },
            }),
          },
        );
        if (!response.ok) {
          // `limit_exceeded` (409, the working-set cap) included — no silent drop is allowed; the
          // typed error surface itself, not a silent drop; the response body's own `options` (the
          // three the cap offers) are not yet rendered here — flagged, not solved, by this fix.
          throw new Error(`Expand failed (${response.status}). Try again.`);
        }
      } catch (err) {
        setActionError({
          x,
          y,
          message: err instanceof Error ? err.message : String(err),
        });
        return;
      }
      const outcome = await response.json();
      store.getState().applyDelta(outcome.delta);
    }

    // `08_ACCEPTANCE_SCENARIOS.md` B11: "a SAME_AS with
    // score 1.0, provenance asserted, attributed to the analyst" — attribution needs no plumbing
    // here beyond the same `bearerToken` `expandNode` already sends, since `link_resolution_route`/
    // `split_resolution_route` (`services/api/app.py`) resolve the writing principal from that same
    // bearer token's own `PrincipalDep`, never a service identity. Both routes return the same
    // `DeltaReproject` shape `set_resolution_threshold` already does, so `applyDelta` needs no new
    // handling for it. `node_a`/`node_b` are sent flat, not wrapped in `{request: ...}` the way
    // `/expand`'s own `ExpandBody` is — `ManualAssertionRequest` (`services/api/resolution.py`) is
    // the whole body, checked directly rather than assumed from `expandNode`'s own different shape.
    async function toggleSuppressionMark(nodeId: string): Promise<void> {
      // A write, like `manualAssertion` — so a failure is surfaced rather than swallowed. An
      // analyst who believes they have flagged a record for suppression, and has not, is exactly
      // the dangerous silence that function's own comment describes.
      const marked = Boolean(suppressionMarks[nodeId]);
      const reason = marked ? "" : "Marked from the canvas";
      try {
        const response = await fetch(
          `${apiBaseUrl}/v1/nodes/${nodeId}/suppression-mark`,
          marked
            ? {
                method: "DELETE",
                headers: { Authorization: `Bearer ${bearerToken}` },
              }
            : {
                method: "POST",
                headers: {
                  Authorization: `Bearer ${bearerToken}`,
                  "Content-Type": "application/json",
                },
                body: JSON.stringify({
                  investigation_id: investigationId,
                  reason,
                }),
              },
        );
        if (!response.ok) {
          throw new Error(
            `${marked ? "Removing the" : "Adding the"} suppression mark failed (${response.status}). Not recorded — try again.`,
          );
        }
      } catch (err) {
        const anchor = radialMenu ?? { x: 0, y: 0 };
        setActionError({
          x: anchor.x,
          y: anchor.y,
          message: err instanceof Error ? err.message : String(err),
        });
        return;
      }
      setSuppressionMarks((current) => {
        const next = { ...current };
        if (marked) delete next[nodeId];
        else next[nodeId] = reason;
        return next;
      });
    }

    async function manualAssertion(
      nodeA: string,
      nodeB: string,
      kind: "link" | "split",
      x: number,
      y: number,
    ): Promise<void> {
      // Fixed first, ahead of expandNode/explainCluster below (CLAUDE.md's own session priority):
      // this is a write, not a read. A silently-dropped expand/explain misleads an analyst about
      // what the data shows; a silently-dropped manualAssertion leaves them believing a link (or
      // split) is recorded in the case when it is not — the more dangerous silence of the three.
      let response: Response;
      try {
        response = await fetch(
          `${apiBaseUrl}/v1/investigations/${investigationId}/resolution/${kind}`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${bearerToken}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ node_a: nodeA, node_b: nodeB }),
          },
        );
        if (!response.ok) {
          const verb = kind === "link" ? "Link" : "Split";
          throw new Error(
            `${verb} failed (${response.status}). Not recorded — try again.`,
          );
        }
      } catch (err) {
        setActionError({
          x,
          y,
          message: err instanceof Error ? err.message : String(err),
        });
        return;
      }
      const delta = await response.json();
      store.getState().applyDelta(delta);
    }

    // `08_ACCEPTANCE_SCENARIOS.md` B10: "per-comparison match
    // weights, not just the total." A `GET`, unlike `expandNode`/`manualAssertion` — `explain_cluster`
    // is a pure read of the working set's own last-computed clustering, nothing to attribute to this
    // principal beyond the bearer token every other read here already sends.
    async function explainCluster(
      clusterId: string,
      x: number,
      y: number,
    ): Promise<void> {
      let response: Response;
      try {
        response = await fetch(
          `${apiBaseUrl}/v1/investigations/${investigationId}/resolution/explain/${clusterId}`,
          { headers: { Authorization: `Bearer ${bearerToken}` } },
        );
        if (!response.ok) {
          // A stale cluster id 404s (`ClusterNotFoundError`, access control's own indistinguishable-
          // from-never-existed shape) — worth saying plainly rather than leaving the analyst to
          // wonder why nothing happened, the same reasoning `PathfinderOverlay`'s own "No path
          // found" already gives for a different, but equally silent-by-default, empty outcome.
          throw new Error(
            `Explain cluster failed (${response.status}). Try again.`,
          );
        }
      } catch (err) {
        setActionError({
          x,
          y,
          message: err instanceof Error ? err.message : String(err),
        });
        return;
      }
      const explanation: ClusterExplanation = await response.json();
      setClusterExplain({ x, y, explanation });
    }

    // Phase 7 Stage 5 (the pathfinder) — `06_DECISIONS.md` ADR-033. `POST /v1/paths` is a bare,
    // non-investigation-scoped query (the same reasoning `/v1/search` already has: it searches the
    // whole access-filtered corpus, not this investigation's own working set), so the result must be
    // seeded into this working set before it can be drawn on-path at all — reusing the existing
    // `/seed` endpoint exactly, not a new working-set-service method. Only nodes/edges not already
    // present are sent; `/seed` itself is idempotent-by-id on the store side regardless.
    async function findPaths(
      nodeA: string,
      nodeB: string,
      x: number,
      y: number,
    ): Promise<void> {
      let response: Response;
      try {
        response = await fetch(`${apiBaseUrl}/v1/paths`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${bearerToken}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            source: nodeA,
            target: nodeB,
            max_hops: 6,
            k: 5,
          }),
        });
        if (!response.ok) {
          throw new Error(
            `Path search failed (${response.status}). Try again.`,
          );
        }
      } catch (err) {
        // Not "No path found" (`pathResult`'s own zero-length case, a completed search) — the
        // search did not complete at all, and folding the two together would tell the analyst
        // something the system does not actually know (`06_DECISIONS.md` ADR-033's own "FIRST"
        // reasoning: this searches the whole access-filtered corpus, a real claim worth getting
        // right). Matches `patterns/api.ts`'s own `throw` shape, not `if (!response.ok) return;`.
        setPathError({
          x,
          y,
          message: err instanceof Error ? err.message : String(err),
        });
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
        const newNodes = [...nodesById.values()].filter(
          (n) => !graph.hasNode(n.id),
        );
        const newEdges = [...edgesById.values()].filter(
          (e) => !graph.hasEdge(e.id),
        );
        if (newNodes.length > 0 || newEdges.length > 0) {
          const seedResponse = await fetch(
            `${apiBaseUrl}/v1/investigations/${investigationId}/seed`,
            {
              method: "POST",
              headers: {
                Authorization: `Bearer ${bearerToken}`,
                "Content-Type": "application/json",
              },
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
        const nextIndex =
          (prev.activeIndex + direction + prev.paths.length) %
          prev.paths.length;
        return { ...prev, activeIndex: nextIndex };
      });
    }

    function dismissPathfinderResult(): void {
      setPathResult(null);
    }

    function dismissPathError(): void {
      setPathError(null);
    }

    function dismissActionError(): void {
      setActionError(null);
    }

    // Fetches the real per-edge-type cardinality for whichever node the radial menu just opened
    // on. One `/expand/preview` call per edge type valid for that node's type — the route is
    // explicitly non-mutating (`working_set/service.py`: "never calls `_add`"), so this is safe to
    // fire on every open.
    //
    // Counts are cleared first, so reopening the menu on a different node never shows the previous
    // node's numbers while the new ones are in flight. A failed or superseded call leaves its entry
    // `null` — the menu shows `…` and the action stays available, since a preview that cannot be
    // fetched is a reason to say so, not a reason to block the expansion behind it.
    useEffect(() => {
      if (!radialMenu || !apiBaseUrl || !bearerToken) return;
      const nodeId = radialMenu.nodeId;
      if (!graph.hasNode(nodeId)) return;
      const node = graph.getNodeAttribute(nodeId, "data");
      const valid = edgeTypesOfferedFor(edgeTypes, node.type);

      let cancelled = false;
      setPreviewCounts({});

      void Promise.all(
        valid.map(async (et) => {
          try {
            const response = await fetch(
              `${apiBaseUrl}/v1/investigations/${investigationId}/expand/preview`,
              {
                method: "POST",
                headers: {
                  Authorization: `Bearer ${bearerToken}`,
                  "Content-Type": "application/json",
                },
                body: JSON.stringify({
                  request: {
                    node_ids: [nodeId],
                    depth: 1,
                    edge_types: [et.name],
                  },
                }),
              },
            );
            if (!response.ok) {
              if (!cancelled)
                setPreviewCounts((prev) => ({
                  ...prev,
                  [et.name]: previewCountFrom({ ok: false }, 0),
                }));
              return;
            }
            const preview = (await response.json()) as {
              candidate_node_count: number;
            };
            if (cancelled) return;
            // `candidate_node_count` is the working set's size *after* this expansion, so the
            // figure the analyst wants — how many this click would add — is the difference.
            const wouldAdd = previewCountFrom(
              { ok: true, candidateNodeCount: preview.candidate_node_count },
              graph.order,
            );
            setPreviewCounts((prev) => ({ ...prev, [et.name]: wouldAdd }));
          } catch {
            // Said as "count unavailable", not left as `…` (which reads as still loading).
            // Deliberately not surfaced as an action error — a preview is an aid, and failing to
            // get one must not block the expansion itself.
            if (!cancelled)
              setPreviewCounts((prev) => ({
                ...prev,
                [et.name]: previewCountFrom({ ok: false }, 0),
              }));
          }
        }),
      );

      return () => {
        cancelled = true;
      };
    }, [
      radialMenu,
      apiBaseUrl,
      bearerToken,
      investigationId,
      graph,
      edgeTypes,
    ]);

    function radialMenuItems(nodeId: string): RadialMenuItem[] {
      if (!graph.hasNode(nodeId)) return [];
      const node = graph.getNodeAttribute(nodeId, "data");
      const valid = edgeTypesOfferedFor(edgeTypes, node.type);
      const items: RadialMenuItem[] = valid.map((et: EdgeTypeDef) => ({
        id: et.name,
        label: et.name,
        // The real figure from `/expand/preview`, fetched by the effect below when this menu
        // opened. `null` (still in flight, or the preview failed) renders as `…`, never as `0`:
        // a confident zero on a node with eight associates is the exact fault this replaced.
        count: previewCounts[et.name] ?? null,
        onSelect: () => {
          const anchor = radialMenu ?? { x: 0, y: 0 };
          void requestExpansion(nodeId, et.name, anchor.x, anchor.y);
        },
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
              count: undefined,
              onSelect: () => {
                const anchor = radialMenu ?? { x: 0, y: 0 };
                void manualAssertion(nodeId, other, "link", anchor.x, anchor.y);
              },
            },
            {
              id: "manual-split",
              label: `Split from ${other}`,
              count: undefined,
              onSelect: () => {
                const anchor = radialMenu ?? { x: 0, y: 0 };
                void manualAssertion(
                  nodeId,
                  other,
                  "split",
                  anchor.x,
                  anchor.y,
                );
              },
            },
            {
              // Phase 7 Stage 5 — the same pair-selection shape B11 above already established,
              // reused rather than a new selection mechanism invented for it.
              id: "find-paths",
              label: `Find paths to ${other}`,
              count: undefined,
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
          if ((attrs.data.resolution?.cluster_id ?? otherId) === clusterId)
            clusterSize += 1;
        });
        if (clusterSize > 1) {
          items.push({
            id: "explain-cluster",
            label: "Explain cluster",
            count: undefined,
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
          count: undefined,
          onSelect: () => void onViewMessages(nodeId),
        });
      }

      // **Owner ruling R7 (TENTATIVE, 27 September 2026) — step one of two.** Offered on every
      // node, not gated on a pair or a type: any record can be proposed for suppression.
      // Marking suppresses nothing — `02_GLASS_FRONTEND.md` §9.5 and
      // `services/api/suppression.py` both say why the mark is deliberately not a graph write —
      // and the item toggles, because R7's own word is "reversible".
      items.push({
        id: "mark-for-suppression",
        label: suppressionMarks[nodeId]
          ? "Remove suppression mark"
          : "Mark for suppression",
        count: undefined,
        onSelect: () => void toggleSuppressionMark(nodeId),
      });

      return items;
    }

    // Selecting a link clears the node selection (and the other way round, in the effect above), and
    // tells the caller, whose Inspector shows the link.
    function selectLink(edgeId: string | null): void {
      setSelectedEdge(edgeId);
      if (edgeId !== null) {
        setSelected(new Set());
        onSelectionChange?.([]);
      }
      onEdgeSelect?.(
        edgeId !== null && graph.hasEdge(edgeId)
          ? graph.getEdgeAttribute(edgeId, "data")
          : null,
      );
    }
    selectLinkRef.current = selectLink;

    // Hiding a link is a view setting for this browser tab: nothing is sent to the server, and
    // it is not in History. "Show hidden links" brings them all back; so does reloading.
    function hideSelectedLink(): void {
      if (selectedEdge === null) return;
      const hide = selectedEdge;
      setHiddenEdges((current) => new Set(current).add(hide));
      selectLink(null);
    }

    // Takes nodes out of the view (the working set); the records stay in the store and the server
    // records a History step. The graph only changes once the server has confirmed: a failure is
    // shown, and the nodes stay where they are.
    async function removeNodeIds(requested: string[]): Promise<void> {
      // A Group Node stands for every node in its group. Removing only the stand-in would take one
      // node out of the group without the analyst having seen it, so unless the whole group is
      // being removed the group is opened instead and the stand-in is left alone.
      const nodeIds = requested.filter((id) => {
        const group = foldedViewRef.current?.groups.get(id);
        if (!group) return true;
        const owner = communities.find((c) => c.id === group.communityId);
        if (owner && owner.members.every((m) => requested.includes(m))) return true;
        unfoldGroup(group.communityId);
        return false;
      });
      if (nodeIds.length === 0) return;
      const result = await removeFromWorkingSet(fetch, {
        apiBaseUrl,
        bearerToken,
        investigationId,
        nodeIds,
      });
      if (!result.ok) {
        const rect = containerRef.current?.getBoundingClientRect();
        setActionError({
          x: (rect?.left ?? 0) + 40,
          y: (rect?.top ?? 0) + 40,
          message: result.message,
        });
        return;
      }
      store
        .getState()
        .applyDelta({ seq: result.seq, op: "remove", node_ids: nodeIds });
      setSelected(new Set());
      setFocused(null);
      onSelectionChange?.([]);
      selectLink(null);
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
        style={{
          width: "100%",
          height: "100%",
          position: "relative",
          outline: "none",
        }}
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
          const polygon = lassoPoints.map((p) => ({
            x: p.x - containerRect.left,
            y: p.y - containerRect.top,
          }));
          const inside = new Set<string>();
          graph.forEachNode((nodeId, attrs) => {
            if (isHiddenInGroup(nodeId)) return;
            const viewport = sigma.graphToViewport({
              x: attrs.x ?? 0,
              y: attrs.y ?? 0,
            });
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
          <svg
            style={{
              position: "absolute",
              inset: 0,
              pointerEvents: "none",
              zIndex: 9,
            }}
          >
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
            title={
              graph.hasNode(radialMenu.nodeId)
                ? `${graph.getNodeAttribute(radialMenu.nodeId, "data").type}: ${nodeLabel(
                    graph.getNodeAttribute(radialMenu.nodeId, "data"),
                  )}`
                : undefined
            }
            items={radialMenuItems(radialMenu.nodeId)}
            onClose={() => setRadialMenu(null)}
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
        {judgementCounts && judgementCounts.size > 0 && (
          <JudgementBadgeOverlay
            sigmaRef={sigmaRef}
            counts={judgementCounts}
            positionOf={(nodeId) => {
              const sigma = sigmaRef.current;
              if (!sigma || !graph.hasNode(nodeId) || isHiddenInGroup(nodeId)) return null;
              return sigma.graphToViewport({
                x: graph.getNodeAttribute(nodeId, "x") ?? 0,
                y: graph.getNodeAttribute(nodeId, "y") ?? 0,
              });
            }}
          />
        )}
        {communitiesOn && (
          <CommunityBoxOverlay
            sigmaRef={sigmaRef}
            getBoxes={() => currentBoxesRef.current()}
            onFold={foldGroup}
          />
        )}
        <CommunitiesControls
          on={communitiesOn}
          groupCount={communities.length}
          foldedCount={collapsed.size}
          onToggle={() => setCommunitiesOn((v) => !v)}
          onCollapseAll={() => setCollapsed(new Set(communities.map((c) => c.id)))}
          onExpandAll={() => setCollapsed(new Set())}
        />
        <LayoutMenu
          mode={layoutMode}
          onChange={(mode) => {
            layoutModeRef.current = mode;
            setLayoutMode(mode);
            arrangeNowRef.current();
          }}
          onArrange={() => arrangeNowRef.current()}
        />
        <ViewActions
          nodeCount={graph.order}
          selectedCount={selected.size}
          onRemoveSelected={() => void removeNodeIds(Array.from(selected))}
          onClearAll={() => void removeNodeIds(graph.nodes())}
          selectedLink={selectedEdge !== null}
          hiddenLinkCount={hiddenEdges.size}
          onHideLink={hideSelectedLink}
          onShowHiddenLinks={() => setHiddenEdges(new Set())}
        />
        {actionError && (
          <ActionErrorOverlay
            x={actionError.x}
            y={actionError.y}
            message={actionError.message}
            onClose={dismissActionError}
          />
        )}
        {pendingExpansion && (
          <LargeExpansionPrompt
            x={pendingExpansion.x}
            y={pendingExpansion.y}
            wouldAdd={pendingExpansion.wouldAdd}
            options={pendingExpansion.options}
            subject={
              graph.hasNode(pendingExpansion.nodeId)
                ? nodeLabel(graph.getNodeAttribute(pendingExpansion.nodeId, "data"))
                : undefined
            }
            relationship={pendingExpansion.edgeType}
            onChooseType={(edgeType) => {
              const { nodeId, x, y, depth } = pendingExpansion;
              setPendingExpansion(null);
              void expandNode(nodeId, edgeType, x, y, depth);
            }}
            onChooseAll={() => {
              const { nodeId, edgeType, x, y, depth } = pendingExpansion;
              setPendingExpansion(null);
              void expandNode(nodeId, edgeType, x, y, depth);
            }}
            onCancel={() => setPendingExpansion(null)}
          />
        )}
      </div>
    );
  },
);
