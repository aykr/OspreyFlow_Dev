// The row-template canvas — `docs/09_INGEST_STUDIO.md` §4: "The studio
// renders it with the same Sigma canvas used everywhere else, so the
// template looks like the thing it will produce." A small, dedicated
// graphology+Sigma instance, not `../../canvas/GlassCanvas.tsx` — that one
// is bound to a live `WorkingSetGraph`/zustand store, investigation-scoped
// deltas and real `Node`/`Edge` handling, none of which exists for a
// template being drafted. A row template is single digits of nodes, so a
// deterministic left-to-right layout (creation order) is enough; no
// ForceAtlas2, no image-node SVG generation — plain circles coloured by
// `OntologyRegistry`'s own channel, so an `Endpoint` here reads as the same
// `Endpoint` the Glass renders once this recipe runs.
import Graph from "graphology";
import Sigma from "sigma";
import { useEffect, useRef } from "react";

import type { OntologySchema, RowTemplate } from "../../../../../packages/schemas/generated";
import { resolveChannelHex } from "../../color/tokens";

export type MapSelection = { kind: "entity"; ref: string } | { kind: "edge"; index: number } | null;

export interface MapCanvasProps {
  template: RowTemplate;
  ontology: OntologySchema;
  selection: MapSelection;
  /** Set while "+ link" is armed and one endpoint has already been picked —
   * that node is highlighted so the analyst can see what the next click
   * will connect. */
  linkFromRef: string | null;
  onSelect: (selection: MapSelection) => void;
  onBackgroundClick: () => void;
}

const NODE_SIZE = 14;
const SELECTED_COLOR = "#c08a34"; // --brass, the same selection accent used elsewhere
const LINK_FROM_COLOR = "#5b9bd5";
const UNKNOWN_TYPE_COLOR = "#8a8f90";

function layoutPosition(index: number): { x: number; y: number } {
  // Left-to-right in creation order — matches §4's own mockup, which draws
  // the row template as a simple flow rather than a force-directed cluster.
  return { x: index * 220, y: (index % 2) * 90 };
}

export function MapCanvas({
  template,
  ontology,
  selection,
  linkFromRef,
  onSelect,
  onBackgroundClick,
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph>(new Graph());

  // `sigma.on(...)` below is wired once, in a mount-only effect, so the
  // Sigma instance survives every re-render (recreating it on every
  // keystroke would flash the canvas and reset the camera). That means its
  // callbacks close over whatever `onSelect`/`onBackgroundClick` were at
  // mount time — stale by the next render, which broke exactly the
  // interaction this canvas exists for: a live click during "+ link" mode
  // was still landing on the *first* render's `handleCanvasSelect`, which
  // read `linking` as permanently `false` and fell through to a plain
  // selection instead of arming the link. Refs sidestep this: the mount-only
  // handler always calls through `.current`, which this effect keeps fresh.
  const onSelectRef = useRef(onSelect);
  const onBackgroundClickRef = useRef(onBackgroundClick);
  useEffect(() => {
    onSelectRef.current = onSelect;
    onBackgroundClickRef.current = onBackgroundClick;
  }, [onSelect, onBackgroundClick]);

  useEffect(() => {
    if (!containerRef.current) return;
    const sigma = new Sigma(graphRef.current, containerRef.current, {
      renderLabels: true,
      defaultNodeColor: UNKNOWN_TYPE_COLOR,
      defaultEdgeColor: "#8a8f90",
    });
    sigmaRef.current = sigma;
    sigma.on("clickNode", ({ node }) => onSelectRef.current({ kind: "entity", ref: node }));
    sigma.on("clickEdge", ({ edge }) => {
      const index = graphRef.current.getEdgeAttribute(edge, "templateIndex") as number;
      onSelectRef.current({ kind: "edge", index });
    });
    sigma.on("clickStage", () => onBackgroundClickRef.current());
    return () => {
      sigma.kill();
      sigmaRef.current = null;
    };
    // Constructed once; the graph's own content is synced by the effect
    // below via `graphRef`, not by recreating the Sigma instance.
  }, []);

  useEffect(() => {
    const graph = graphRef.current;
    graph.clear();
    template.entities.forEach((entity, index) => {
      const visual = ontology.entity_types.find((t) => t.name === entity.type);
      const { x, y } = layoutPosition(index);
      const isSelected = selection?.kind === "entity" && selection.ref === entity.ref;
      const isLinkFrom = linkFromRef === entity.ref;
      graph.addNode(entity.ref, {
        label: `${entity.ref} · ${entity.type}`,
        x,
        y,
        size: NODE_SIZE,
        color: isSelected
          ? SELECTED_COLOR
          : isLinkFrom
            ? LINK_FROM_COLOR
            : visual
              ? resolveChannelHex(visual.channel)
              : UNKNOWN_TYPE_COLOR,
      });
    });
    (template.edges ?? []).forEach((edge, index) => {
      if (!graph.hasNode(edge.from) || !graph.hasNode(edge.to)) return;
      const isSelected = selection?.kind === "edge" && selection.index === index;
      // Plain straight-line edges — the same simplification
      // `../../canvas/GlassCanvas.tsx` discloses (no `@sigma/edge-curve`
      // wired), and directionality is legible enough here from the
      // inspector's own `from`/`to` fields for a template this small.
      graph.addEdgeWithKey(`edge-${index}`, edge.from, edge.to, {
        label: edge.type,
        size: isSelected ? 4 : 2,
        color: isSelected ? SELECTED_COLOR : "#8a8f90",
        templateIndex: index,
      });
    });
    sigmaRef.current?.refresh();
  }, [template, ontology, selection, linkFromRef]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label="Row template canvas"
      style={{ width: "100%", height: "100%", minHeight: 320 }}
    />
  );
}
