// Turns a domain `Node`/`Edge` plus its current interaction/filter/zoom
// context into Sigma-ready display attributes — `docs/02_GLASS_FRONTEND.md`
// §4's node-state vocabulary and §1.1's semantic zoom, wired together for
// real (`docs/07_BUILD_PLAN.md` Phase 4, Checkpoint 2).
//
// **Two different attribute pipelines, deliberately split.** Sigma's
// `nodeReducer` return type (`Partial<NodeDisplayData>`) is a *fixed*
// shape — `size`/`label`/`hidden`/`color`/`x`/`y` — it has no slot for a
// custom program's own attributes. `@sigma/node-image`'s `imageAttribute`
// and `@sigma/node-border`'s per-border `color`/`size` specs instead read
// directly off the graphology node's *stored* attributes, not off
// whatever the reducer returns. So:
//   - `computeNodeFrameAttributes` — called every frame, per node, from
//     the reducer: size and label-eligibility, which are zoom-band
//     (`cameraRatio`) dependent and must react every frame the camera
//     moves.
//   - `computeNodeGraphAttributes` — called imperatively, only when a
//     node's *own* dimming/provenance/interaction state actually changes
//     (a filter application, a hover, a selection) — never once per
//     frame, since none of those change on every render. The caller
//     writes this onto the graph with `graph.mergeNodeAttributes`.
// Colour is entity type, always: `computeNodeGraphAttributes` is the only
// place fill colour is decided, and it is a function of `visual.channel`
// and dimming state alone — nothing here ever derives a fill from a
// metric, a degree or a filter *value* (only filter *presence*, dimmed
// vs. not, which the token contract itself specifies).
import type { Edge, Node } from "../../../../packages/schemas/generated";
import { cachedNodeSvgDataUri, type StrokeStyle } from "../color/nodeVisual";
import { mixOklab } from "../color/oklab";
import {
  BORDER_STRONG_DARK_HEX,
  BRASS_HEX,
  resolveChannelHex,
  SURFACE_PANEL_DARK_HEX,
  TEXT_PRIMARY_DARK_HEX,
} from "../color/tokens";
import type { EntityVisual } from "../ontology/schema";
import { zoomBandForRatio, type ZoomBand } from "./zoomBands";

export interface NodeZoomContext {
  cameraRatio: number;
  degree: number;
}

export interface NodeFrameAttributes {
  size: number;
  label: string;
  hidden: false;
}

const BAND_SIZE: Record<ZoomBand, number> = {
  overview: 3,
  structure: 5,
  neighbourhood: 6,
  "link-detail": 8,
};

function nodeLabel(node: Node): string {
  const name = node.properties?.["family_name"] ?? node.properties?.["value_normalised"];
  return typeof name === "string" ? name : node.id;
}

/** Called from `Sigma`'s `nodeReducer`, every node, every frame the
 * camera moves — kept to simple lookups and arithmetic, no image
 * generation or colour maths here. Nodes are never `hidden` by zoom
 * (`docs/02_GLASS_FRONTEND.md` §1.1: "Zoom never changes what exists,
 * only what is drawn" — even Overview draws every node, just small). */
export function computeNodeFrameAttributes(node: Node, context: NodeZoomContext): NodeFrameAttributes {
  const band = zoomBandForRatio(context.cameraRatio);
  const labelEligible = band !== "overview" && (band !== "structure" || context.degree > 10);
  return { size: BAND_SIZE[band], label: labelEligible ? nodeLabel(node) : "", hidden: false };
}

export interface NodeVisualState {
  /** Filter state — always `false` in Phase 4 (no filter panel exists
   * yet, Phase 5's bullet); included now so the shape is right when a
   * filter reducer lands rather than being retrofitted later. */
  dimmed: boolean;
  filteredOut: boolean;
  hovered: boolean;
  selected: boolean;
  onPath: boolean;
}

export interface NodeGraphAttributes {
  image: string;
  color: string;
  borderColor: string;
  borderSize: number;
}

function provenanceStroke(node: Node, channelHex: string): { style: StrokeStyle; hex: string } {
  const state = node.provenance.state;
  if (state === "asserted") return { style: "solid", hex: BORDER_STRONG_DARK_HEX };
  if (state === "inferred") return { style: "dashed", hex: channelHex };
  return { style: "dotted", hex: channelHex }; // "unresolved"
}

/** Called imperatively (`graph.mergeNodeAttributes`) whenever a node's own
 * dimming, provenance or interaction state changes — not per frame. */
export function computeNodeGraphAttributes(
  node: Node,
  visual: EntityVisual,
  state: NodeVisualState,
): NodeGraphAttributes {
  const channelHex = resolveChannelHex(visual.channel);
  const fillHex = state.filteredOut
    ? mixOklab(channelHex, SURFACE_PANEL_DARK_HEX, 12)
    : state.dimmed
      ? mixOklab(channelHex, SURFACE_PANEL_DARK_HEX, 32)
      : channelHex;

  const stroke = provenanceStroke(node, channelHex);
  const image = cachedNodeSvgDataUri({
    shape: visual.shape,
    fillHex,
    strokeHex: stroke.hex,
    strokeStyle: stroke.style,
  });

  // Interaction-state ring — `@sigma/node-border`'s own layer, never
  // baked into `image`: on-path first (path highlighting takes priority
  // over a merely-hovered node on that path), then selected, then hover.
  const { borderColor, borderSize } = state.onPath
    ? { borderColor: TEXT_PRIMARY_DARK_HEX, borderSize: 2 }
    : state.selected
      ? { borderColor: BRASS_HEX, borderSize: 2 }
      : state.hovered
        ? { borderColor: TEXT_PRIMARY_DARK_HEX, borderSize: 1.5 }
        : { borderColor: "transparent", borderSize: 0 };

  return { image, color: fillHex, borderColor, borderSize };
}

export interface EdgeRenderContext {
  cameraRatio: number;
  strengthFilterFloor: number;
}

export interface ResolvedEdgeAttributes {
  size: number;
  color: string;
  label: string;
  hidden: boolean;
}

export function computeEdgeAttributes(
  edge: Edge,
  context: EdgeRenderContext,
): ResolvedEdgeAttributes {
  const band = zoomBandForRatio(context.cameraRatio);
  const weight = edge.weight ?? 1;
  const belowStrengthFilter = weight < context.strengthFilterFloor;

  if (band === "overview") {
    return { size: 1, color: BORDER_STRONG_DARK_HEX, label: "", hidden: belowStrengthFilter };
  }
  const size = Math.max(1, Math.min(4, weight * 2));
  return {
    size,
    color: BORDER_STRONG_DARK_HEX,
    label: band === "link-detail" ? `${edge.type} (${edge.occurrences ?? 1})` : "",
    hidden: false,
  };
}
