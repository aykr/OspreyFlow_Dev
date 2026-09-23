// Semantic zoom — `docs/02_GLASS_FRONTEND.md` §1.1, `docs/06_DECISIONS.md`
// ADR-002's own acceptance condition.
//
// **This module must never import `workingset/store.ts`.** That is not a
// style preference — it is the structural half of "zoom never changes
// what exists, only what is drawn": a `nodeReducer`/`edgeReducer` that
// cannot reach the store's mutation API cannot accidentally call it,
// regardless of what a future edit tries to do inside this file. The
// runtime half of the same proof lives in `zoomBands.test.ts`, which
// drives a real working set through all four bands and asserts
// `graph.order`/`graph.size` never change. Checkpoint 2 wires the full
// visual vocabulary (§4's nine channels, three provenance strokes, six
// interaction states) into these reducers; this file is the band
// computation and the reducer *shape* only — Sigma's actual node/edge
// programs are a separate, later change.

export type ZoomBand = "overview" | "structure" | "neighbourhood" | "link-detail";

/**
 * Camera-ratio → band thresholds. Illustrative for this checkpoint —
 * Checkpoint 2 tunes the exact cut points against a real Sigma camera and
 * §1.1's "never coincide with the natural resting zoom of a common
 * layout" rule, which needs an actual rendered graph to check against,
 * not a unit test.
 */
const BAND_THRESHOLDS: ReadonlyArray<{ maxRatio: number; band: ZoomBand }> = [
  { maxRatio: 0.15, band: "link-detail" },
  { maxRatio: 0.4, band: "neighbourhood" },
  { maxRatio: 1.2, band: "structure" },
  { maxRatio: Number.POSITIVE_INFINITY, band: "overview" },
];

export function zoomBandForRatio(ratio: number): ZoomBand {
  for (const { maxRatio, band } of BAND_THRESHOLDS) {
    if (ratio <= maxRatio) return band;
  }
  /* istanbul ignore next -- BAND_THRESHOLDS always ends in Infinity */
  return "overview";
}

export interface NodeReducerInput {
  /** Whichever properties a future reducer needs from `data` — kept
   * generic here since Checkpoint 1 does not yet map the domain `Node`
   * onto the nine-channel vocabulary. */
  degree: number;
}

export interface NodeDisplayAttributes {
  hidden: boolean;
  labelEligible: boolean;
}

export interface EdgeReducerInput {
  weight: number;
}

export interface EdgeDisplayAttributes {
  hidden: boolean;
  labelEligible: boolean;
}

/**
 * `nodeReducer` — Sigma calls this per node per frame with the current
 * camera ratio; it returns *display* attributes only. It has no
 * `graph` parameter and no store reference: it cannot draw on anything
 * but what the caller already handed it, by construction.
 */
export function nodeReducer(input: NodeReducerInput, cameraRatio: number): NodeDisplayAttributes {
  const band = zoomBandForRatio(cameraRatio);
  switch (band) {
    case "overview":
      return { hidden: false, labelEligible: false };
    case "structure":
      return { hidden: false, labelEligible: input.degree > 10 };
    case "neighbourhood":
    case "link-detail":
      return { hidden: false, labelEligible: true };
  }
}

/**
 * `edgeReducer` — same contract as `nodeReducer`. `hideEdgesOnMove`
 * (§1.1's frame-budget technique during camera movement) is a Sigma
 * setting toggled by the canvas's camera-move handlers, not a band
 * decision this function makes — it always returns this band's *at-rest*
 * visibility.
 */
export function edgeReducer(input: EdgeReducerInput, cameraRatio: number): EdgeDisplayAttributes {
  const band = zoomBandForRatio(cameraRatio);
  switch (band) {
    case "overview":
      return { hidden: input.weight <= 0, labelEligible: false };
    case "structure":
    case "neighbourhood":
      return { hidden: false, labelEligible: false };
    case "link-detail":
      return { hidden: false, labelEligible: true };
  }
}
