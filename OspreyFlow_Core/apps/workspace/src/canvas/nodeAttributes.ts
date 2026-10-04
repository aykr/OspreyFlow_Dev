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
import { resolveNodeIcon } from "./iconChoices";
import { chosenLabel, defaultLabel } from "./labelChoices";
import { linkCaption, linkTypeName } from "./linkLabel";
import { zoomBandForRatio, type ZoomBand } from "./zoomBands";

export interface NodeZoomContext {
  cameraRatio: number;
  degree: number;
  /** How many nodes are in the view. A crowded view draws them smaller; omitted, full size. */
  viewNodeCount?: number;
  /** The node is selected, under the pointer or on a found path: it is always named. */
  emphasised?: boolean;
}

/** A view of this many nodes or fewer names every node whatever the zoom or the node's links (ADR-071).
 * The zoom rule below exists to keep a crowded view legible; in a small one it only left the analyst
 * unable to tell two nodes apart. A first guess, to be tuned by looking at a real view. */
export const SMALL_VIEW_LABEL_LIMIT = 40;

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
  // The analyst's own choice for this type first (ADR-076), else the default.
  return chosenLabel(node) ?? defaultLabel(node);
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
  const smallView =
    context.viewNodeCount !== undefined && context.viewNodeCount <= SMALL_VIEW_LABEL_LIMIT;
  const labelEligible =
    smallView ||
    context.emphasised === true ||
    (band !== "overview" && (band !== "structure" || context.degree > 10));
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
  /** Selected, under the pointer or on a found path: the canvas names it at any zoom. */
  emphasised: boolean;
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
    // The analyst's own choice for the type, else the ontology's (ADR-079).
    icon: resolveNodeIcon(node.type, visual.icon, fillHex),
    iconOpacity: state.filteredOut ? 0.2 : state.dimmed ? 0.45 : 1,
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

  return {
    image,
    color: fillHex,
    borderColor,
    borderSize,
    emphasised: state.selected || state.hovered || state.onPath,
  };
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
  /** What this link's type declares about how it is drawn (ADR-081): a colour, one of the nine
   * data-channel names, and a thickness from 1 to 5. Omitted or empty, the ordinary colour and the
   * weight-only width apply. A name that is not a channel is ignored rather than drawn. */
  declared?: { colour?: string | null; thickness?: number | null };
  /** The timeline dims this link (ADR-087): no event in the brush window, or not yet reached by the
   * playhead. Drawn as a dimmed node is, mixed towards the panel, label dropped, never removed. */
  dimmed?: boolean;
  /** What the link reads as (ADR-091): "Communicated with · 3 emails". Called only when a label
   * is drawn, so the reducer builds no string for an unlabelled link; omitted, the caption is
   * derived from the type's name with the count as records. */
  caption?: () => string;
}

function edgeCaption(edge: Edge, context: EdgeRenderContext): string {
  return context.caption
    ? context.caption()
    : linkCaption(linkTypeName(edge.type, []), edge.occurrences ?? 1, "events");
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
        band === "link-detail" ? edgeCaption(edge, context) : "",
      hidden: false,
    };
  }

  const crowd = crowdingScale(context.viewEdgeCount);
  const lit = declaredColour(context.declared?.colour, palette);
  const colour = context.dimmed ? mixOklab(lit, palette.surfacePanel, 32) : lit;
  if (band === "overview") {
    return {
      size: Math.max(0.5, crowd),
      color: colour,
      label:
        context.touchesHoveredNode && !belowStrengthFilter && !context.dimmed
          ? edgeCaption(edge, context)
          : "",
      hidden: belowStrengthFilter,
    };
  }
  const thickness = context.declared?.thickness;
  // A declared thickness is the base and the weight scales it, between half and one and a half
  // times (ADR-081, Amendment 1); with none declared, today's weight-only width stands.
  const base =
    typeof thickness === "number" && thickness >= 1 && thickness <= 5
      ? thickness * Math.min(1.5, Math.max(0.5, weight))
      : Math.max(1, Math.min(4, weight * 2));
  const size = Math.max(0.5, base * crowd);
  return {
    size,
    color: colour,
    label:
      (band === "link-detail" || context.touchesHoveredNode) && !context.dimmed
        ? edgeCaption(edge, context)
        : "",
    hidden: false,
  };
}

/** The line colour a type declares, as a hex for the current theme. Only the nine data-channel
 * names are accepted (the closed list in `design/tokens.css`); anything else, or nothing, is the
 * ordinary border colour, so no colour outside the tokens can reach the canvas. */
function declaredColour(name: string | null | undefined, palette: ReturnType<typeof activePalette>): string {
  if (typeof name === "string" && DATA_CHANNEL_NAMES.has(name)) return palette.channel(name);
  return palette.borderStrong;
}

const DATA_CHANNEL_NAMES: ReadonlySet<string> = new Set([
  "ochre",
  "rose",
  "plum",
  "violet",
  "indigo",
  "azure",
  "cyan",
  "jade",
  "moss",
]);

/** The parts of an ontology relationship type that decide how a link of it is drawn. */
export interface EdgeTypeStyle {
  name: string;
  directed?: boolean;
  basis?: "direct" | "probabilistic" | null;
  colour?: string | null;
  thickness?: number | null;
  /** ADR-091: the type's display name in sentence case. */
  label?: string | null;
}

/** What a link's type declares about colour and thickness, for `computeEdgeAttributes`. */
export function declaredFor(
  edgeType: string,
  edgeTypes: readonly EdgeTypeStyle[],
): { colour?: string | null; thickness?: number | null } {
  const def = edgeTypes.find((t) => t.name === edgeType);
  return { colour: def?.colour ?? null, thickness: def?.thickness ?? null };
}

/** The names the Glass registers its edge programs under (`GlassCanvas`). */
export type EdgeProgramName =
  | "glass-edge"
  | "glass-arrow"
  | "glass-edge-thick"
  | "glass-edge-dotted"
  | "glass-arrow-dotted";

export type LinkBasis = "direct" | "probabilistic";

/** What stands behind a link, read from the link and its type together (ADR-081 decision 2, step
 * B). A link of a Probabilistic type is probabilistic whatever is stored on it; a link of a Direct
 * type is direct unless it carries its own probabilistic mark; a type with no basis (`NOT_SAME_AS`,
 * or one the ontology does not know) gives none. The same rule as `schemas.domain.effective_basis`. */
export function effectiveBasis(
  linkBasis: LinkBasis | null | undefined,
  edgeType: EdgeTypeStyle | undefined,
): LinkBasis | null {
  const typeBasis = edgeType?.basis ?? null;
  if (typeBasis === "probabilistic") return "probabilistic";
  if (linkBasis === "probabilistic") return "probabilistic";
  return typeBasis;
}

/** Which Sigma edge program draws this link. An arrowhead only where the ontology says the
 * relationship has a direction (`EdgeTypeDef.directed`): a symmetric type such as `SAME_AS` must
 * not look as if it points one way, and a type the ontology does not know claims no direction.
 * The line style follows the link's basis and is never authored (ADR-081): Probabilistic is always
 * dotted, Direct is always solid, and a link with no basis (`NOT_SAME_AS`, or a type the ontology
 * does not know) is drawn as it always was. The link's own mark counts (step B): a link of a Direct
 * type an analyst marked probabilistic is dotted. A solid undirected type that declares a thickness
 * uses the program that honours width, since the plain line program is one pixel wide whatever its
 * size. */
export function edgeProgramFor(
  edgeType: string,
  edgeTypes: readonly EdgeTypeStyle[],
  linkBasis?: LinkBasis | null,
): EdgeProgramName {
  const def = edgeTypes.find((t) => t.name === edgeType);
  const directed = def?.directed === true;
  if (effectiveBasis(linkBasis, def) === "probabilistic") {
    return directed ? "glass-arrow-dotted" : "glass-edge-dotted";
  }
  if (directed) return "glass-arrow";
  return typeof def?.thickness === "number" ? "glass-edge-thick" : "glass-edge";
}
