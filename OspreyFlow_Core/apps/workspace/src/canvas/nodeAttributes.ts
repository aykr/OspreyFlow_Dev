// Turns a domain `Node`/`Edge` plus its current interaction/filter/zoom
// context into Sigma-ready display attributes — `spec/02_GLASS_FRONTEND.md`
// §4's node-state vocabulary and §1.1's semantic zoom, wired together for
// real.
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
import { BRASS_HEX } from "../color/tokens";
import { activePalette } from "../color/palette";
import type { EntityVisual } from "../ontology/schema";
import { zoomBandForRatio, type ZoomBand } from "./zoomBands";

export interface NodeZoomContext {
  cameraRatio: number;
  degree: number;
  /** How many nodes are in the view. A crowded view draws them smaller; omitted, full size. */
  viewNodeCount?: number;
}

const CROWDING_FROM = 150;
const CROWDING_TO = 3000;
const CROWDING_FLOOR = 0.55;

/** How much to shrink what is drawn for a view this crowded: 1 up to 150 items, falling steadily
 * (on a log scale, since the eye sees the doubling not the sum) to 0.55 at 3,000 and beyond. It
 * depends only on how many there are, so zoom and the data never change what exists, only how
 * loudly it is drawn. */
export function crowdingScale(count: number | undefined): number {
  if (count === undefined || count <= CROWDING_FROM) return 1;
  const t = Math.min(
    1,
    (Math.log(count) - Math.log(CROWDING_FROM)) / (Math.log(CROWDING_TO) - Math.log(CROWDING_FROM)),
  );
  return 1 - (1 - CROWDING_FLOOR) * t;
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

/** Exported for reuse outside the per-frame reducer — `ClusterExplainOverlay` (Phase 6a Stage 3)
 * needs the same human-readable label for a `PairwiseExplanation`'s `node_a`/`node_b`, and
 * duplicating this lookup rather than sharing it would be a second place to keep in sync. */
export function nodeLabel(node: Node): string {
  const name =
    node.properties?.["family_name"] ?? node.properties?.["value_normalised"];
  return typeof name === "string" ? name : node.id;
}

/** Called from `Sigma`'s `nodeReducer`, every node, every frame the
 * camera moves — kept to simple lookups and arithmetic, no image
 * generation or colour maths here. Nodes are never `hidden` by zoom
 * (`spec/02_GLASS_FRONTEND.md` §1.1: "Zoom never changes what exists,
 * only what is drawn" — even Overview draws every node, just small). */
export function computeNodeFrameAttributes(
  node: Node,
  context: NodeZoomContext,
): NodeFrameAttributes {
  const band = zoomBandForRatio(context.cameraRatio);
  const labelEligible =
    band !== "overview" && (band !== "structure" || context.degree > 10);
  return {
    size: Math.max(2, BAND_SIZE[band] * crowdingScale(context.viewNodeCount)),
    label: labelEligible ? nodeLabel(node) : "",
    hidden: false,
  };
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

function provenanceStroke(
  node: Node,
  channelHex: string,
): { style: StrokeStyle; hex: string } {
  const state = node.provenance.state;
  if (state === "asserted")
    return { style: "solid", hex: activePalette().borderStrong };
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
  const palette = activePalette();
  const channelHex = palette.channel(visual.channel);
  const fillHex = state.filteredOut
    ? mixOklab(channelHex, palette.surfacePanel, 12)
    : state.dimmed
      ? mixOklab(channelHex, palette.surfacePanel, 32)
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
    ? { borderColor: palette.textPrimary, borderSize: 2 }
    : state.selected
      ? { borderColor: BRASS_HEX, borderSize: 2 }
      : state.hovered
        ? { borderColor: palette.textPrimary, borderSize: 1.5 }
        : { borderColor: "transparent", borderSize: 0 };

  return { image, color: fillHex, borderColor, borderSize };
}

export interface ClusterGraphAttributes {
  clusterBorderColor: string;
  clusterBorderSize: number;
}

/**
 * Phase 6a Stage 2 (B9): "the number and the picture have to agree" — a node currently
 * collapsed with at least one other under the session's resolution threshold gets a quiet,
 * always-on second ring (`--border-subtle`, never `--brass`/on-path white: those are interaction
 * state, this is a standing fact about the node's own resolution status). A singleton cluster
 * (the ordinary case — no `SAME_AS` above τ) gets no ring at all. Proposed rendering, not spec:
 * `02_GLASS_FRONTEND.md` has no existing convention for resolution-cluster collapse (its own
 * hull overlay is for community detection, a different, unrelated grouping).
 */
export function computeClusterGraphAttributes(
  clusterMemberCount: number,
): ClusterGraphAttributes {
  if (clusterMemberCount <= 1)
    return { clusterBorderColor: "transparent", clusterBorderSize: 0 };
  return { clusterBorderColor: activePalette().borderSubtle, clusterBorderSize: 1 };
}

export interface EdgeRenderContext {
  cameraRatio: number;
  strengthFilterFloor: number;
  /** Phase 7 Stage 5 (the pathfinder) — `02_GLASS_FRONTEND.md` §3.1: "paths render with the
   * on-path node state... edges thickened". Node dimming (32% channel mix, already implemented
   * in `computeNodeGraphAttributes`) is the dominant "everything else" cue for a found path —
   * edges here get only the thickened treatment, not a parallel dimming concept of their own:
   * `ResolvedEdgeAttributes.color` is already a single fixed `--border-strong` hex regardless of
   * any other state, so there is no existing per-edge colour-mix mechanism to extend, and a thin
   * line's own colour barely registers next to a dimmed node's fill in any case. Disclosed
   * simplification, not an oversight. */
  onPath: boolean;
  /** One end of this edge is the node under the pointer. Its label is shown at any zoom, so an
   * analyst can read what a relationship is by pointing at either end of it, without zooming in
   * until every label on the canvas appears at once. */
  touchesHoveredNode?: boolean;
  /** How many links are in the view. A crowded view draws them thinner; omitted, full width. */
  viewEdgeCount?: number;
}

export interface ResolvedEdgeAttributes {
  size: number;
  color: string;
  label: string;
  hidden: boolean;
}

//: Fixed, not weight-derived — an on-path edge must read as thickened regardless of how thin its
//: own weight would otherwise draw it; the ordinary weight-based size tops out at 4
//: (`Math.min(4, weight * 2)` below), so 5 is a real, visible step up rather than an
//: overlap-prone one.
const ON_PATH_EDGE_SIZE = 5;

export function computeEdgeAttributes(
  edge: Edge,
  context: EdgeRenderContext,
): ResolvedEdgeAttributes {
  const band = zoomBandForRatio(context.cameraRatio);
  const palette = activePalette();
  const weight = edge.weight ?? 1;
  const belowStrengthFilter = weight < context.strengthFilterFloor;

  // On-path takes priority over the strength filter and the overview band's own size clamp — the
  // same "path highlighting takes priority" ordering `computeNodeGraphAttributes` already
  // documents for its own border priority (on-path, then selected, then hover).
  if (context.onPath) {
    return {
      size: ON_PATH_EDGE_SIZE,
      color: palette.textPrimary,
      label:
        band === "link-detail" ? `${edge.type} (${edge.occurrences ?? 1})` : "",
      hidden: false,
    };
  }

  const crowd = crowdingScale(context.viewEdgeCount);
  if (band === "overview") {
    return {
      size: Math.max(0.5, crowd),
      color: palette.borderStrong,
      label:
        context.touchesHoveredNode && !belowStrengthFilter
          ? `${edge.type} (${edge.occurrences ?? 1})`
          : "",
      hidden: belowStrengthFilter,
    };
  }
  const size = Math.max(0.5, Math.max(1, Math.min(4, weight * 2)) * crowd);
  return {
    size,
    color: palette.borderStrong,
    label:
      band === "link-detail" || context.touchesHoveredNode
        ? `${edge.type} (${edge.occurrences ?? 1})`
        : "",
    hidden: false,
  };
}

/** Which Sigma edge program draws this edge type: an arrowhead only where the ontology says the
 * relationship has a direction (`EdgeTypeDef.directed`), a plain line otherwise. A symmetric type
 * such as `SAME_AS` must not look as if it points one way, and a type the ontology does not know
 * claims no direction. */
export function edgeProgramFor(
  edgeType: string,
  edgeTypes: readonly { name: string; directed?: boolean }[],
): "glass-arrow" | "glass-edge" {
  return edgeTypes.find((t) => t.name === edgeType)?.directed === true
    ? "glass-arrow"
    : "glass-edge";
}
