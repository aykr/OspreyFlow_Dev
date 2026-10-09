// The row-template canvas — `spec/09_INGEST_STUDIO.md` §4: "The studio
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
import { useEffect, useRef, useState } from "react";

import type { OntologySchema, RowTemplate } from "../../../../../packages/schemas/generated";
import { activePalette } from "../../color/palette";
import { onThemeChange } from "../../theme/theme";
import { mapCanvasColours } from "./mapCanvasColours";
import { syncTemplateGraph } from "./mapGraphSync";

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
  const [themeVersion, setThemeVersion] = useState(0);

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
    const colours = mapCanvasColours(activePalette());
    const sigma = new Sigma(graphRef.current, containerRef.current, {
      renderLabels: true,
      labelColor: { color: colours.label },
      defaultNodeColor: colours.edge,
      defaultEdgeColor: colours.edge,
    });
    sigmaRef.current = sigma;
    sigma.on("clickNode", ({ node }) => onSelectRef.current({ kind: "entity", ref: node }));
    sigma.on("clickEdge", ({ edge }) => {
      const index = graphRef.current.getEdgeAttribute(edge, "templateIndex") as number;
      onSelectRef.current({ kind: "edge", index });
    });
    sigma.on("clickStage", () => onBackgroundClickRef.current());
    // A canvas cannot read a CSS variable, so it is told when the theme changes (ADR-070).
    const stopWatchingTheme = onThemeChange(() => setThemeVersion((v) => v + 1));
    return () => {
      stopWatchingTheme();
      sigma.kill();
      sigmaRef.current = null;
    };
    // Constructed once; the graph's own content is synced by the effect
    // below via `graphRef`, not by recreating the Sigma instance.
  }, []);

  useEffect(() => {
    const palette = activePalette();
    sigmaRef.current?.setSetting("labelColor", { color: mapCanvasColours(palette).label });
    syncTemplateGraph(graphRef.current, template, ontology, selection, linkFromRef, palette);
    sigmaRef.current?.refresh();
  }, [template, ontology, selection, linkFromRef, themeVersion]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label="Row template canvas"
      style={{ width: "100%", height: "100%", minHeight: 320 }}
    />
  );
}
