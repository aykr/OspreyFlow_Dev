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
import { EdgeLineProgram, createNodeCompoundProgram } from "sigma/rendering";
import Sigma from "sigma";
import { useEffect, useRef, useState } from "react";

import type { EdgeTypeDef } from "../../../../packages/schemas/generated";
import type { OntologyRegistry } from "../ontology/schema";
import type {
  WorkingSetEdgeAttributes,
  WorkingSetGraph,
  WorkingSetNodeAttributes,
  WorkingSetStoreState,
} from "../workingset/store";
import {
  computeEdgeAttributes,
  computeNodeFrameAttributes,
  computeNodeGraphAttributes,
} from "./nodeAttributes";
import { RadialMenu, type RadialMenuItem } from "../design/primitives/RadialMenu";
import { EdgeInspectionOverlay } from "./EdgeInspectionOverlay";

const NODE_PROGRAM = createNodeCompoundProgram<WorkingSetNodeAttributes, WorkingSetEdgeAttributes>([
  createNodeImageProgram<WorkingSetNodeAttributes, WorkingSetEdgeAttributes>({
    keepWithinCircle: false,
    drawingMode: "background",
    padding: 0,
  }),
  createNodeBorderProgram<WorkingSetNodeAttributes, WorkingSetEdgeAttributes>({
    borders: [
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
  onSelectionChange?: (nodeIds: string[]) => void;
  /** The keyboard-focused node id (`docs/02_GLASS_FRONTEND.md` §6: "Tab
   * moves between nodes... arrow keys walk edges"), or `null` when
   * nothing has been keyboard-focused yet. Exposed so a caller can, e.g.,
   * highlight the focused node in a legend — and it is what
   * `keyboard/keyboard.spec.ts` observes to prove the keyboard-only
   * walkthrough actually moves focus, rather than asserting on internal
   * component state it has no other way to reach. */
  onFocusChange?: (nodeId: string | null) => void;
}

interface PendingRadialMenu {
  x: number;
  y: number;
  nodeId: string;
  layout: "radial" | "list";
}

export function GlassCanvas({
  graph,
  store,
  ontology,
  edgeTypes,
  investigationId,
  apiBaseUrl,
  bearerToken,
  onSelectionChange,
  onFocusChange,
}: GlassCanvasProps) {
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
  const [lassoActive, setLassoActive] = useState(false);
  const [lassoPoints, setLassoPoints] = useState<{ x: number; y: number }[]>([]);

  const refreshNodeVisualState = (nodeId: string) => {
    if (!graph.hasNode(nodeId)) return;
    const node = graph.getNodeAttribute(nodeId, "data");
    const visual = ontology.visualFor(node.type);
    if (!visual) return;
    const attrs = computeNodeGraphAttributes(node, visual, {
      dimmed: false,
      filteredOut: false,
      hovered: hovered === nodeId,
      selected: selected.has(nodeId),
      onPath: false,
    });
    graph.mergeNodeAttributes(nodeId, attrs);
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
        const attrs = computeEdgeAttributes(data.data, { cameraRatio: ratio, strengthFilterFloor: 0 });
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

  // Keyboard: accessibility floor (`docs/02_GLASS_FRONTEND.md` §6) — every
  // canvas action reachable without a mouse.
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Tab" && selected.size === 0) {
      // The keyboard-only entry point: §6 says "Tab moves between nodes
      // in the current selection ring", which presumes a ring already
      // exists. Without this branch a keyboard-only analyst who has never
      // touched the mouse has no way to reach a first node at all — Tab
      // here establishes a one-node ring (and fires `onSelectionChange`,
      // the same event a mouse click would) so every subsequent
      // documented behaviour (arrows, Enter, `\`) has something to act on.
      e.preventDefault();
      const first = graph.nodes()[0];
      if (first) {
        setSelected(new Set([first]));
        setFocused(first);
        onSelectionChange?.([first]);
      }
    } else if (e.key === "Tab" && selected.size > 0) {
      e.preventDefault();
      const ring = Array.from(selected);
      const currentIndex = focused ? ring.indexOf(focused) : -1;
      const nextIndex = e.shiftKey
        ? (currentIndex - 1 + ring.length) % ring.length
        : (currentIndex + 1) % ring.length;
      setFocused(ring[nextIndex] ?? null);
    } else if ((e.key === "ArrowRight" || e.key === "ArrowDown") && focused) {
      const neighbours = graph.neighbors(focused);
      if (neighbours.length > 0) setFocused(neighbours[0] ?? null);
    } else if ((e.key === "ArrowLeft" || e.key === "ArrowUp") && focused) {
      const neighbours = graph.neighbors(focused);
      if (neighbours.length > 0) setFocused(neighbours[neighbours.length - 1] ?? null);
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

  function radialMenuItems(nodeId: string): RadialMenuItem[] {
    if (!graph.hasNode(nodeId)) return [];
    const node = graph.getNodeAttribute(nodeId, "data");
    const valid = edgeTypes.filter(
      (et) => et.from.includes(node.type) || et.to.includes(node.type),
    );
    return valid.map((et) => ({
      id: et.name,
      label: et.name,
      count: 0, // populated by expand/preview in a follow-up pass, not blocking the action itself
      onSelect: () => void expandNode(nodeId, et.name),
    }));
  }

  return (
    <div
      ref={containerRef}
      role="application"
      aria-label="Network canvas"
      tabIndex={0}
      onKeyDown={onKeyDown}
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
    </div>
  );
}

function pointInPolygon(point: { x: number; y: number }, polygon: { x: number; y: number }[]): boolean {
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
