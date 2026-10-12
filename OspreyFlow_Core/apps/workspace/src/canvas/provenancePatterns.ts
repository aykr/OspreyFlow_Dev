// A link's provenance pattern, in screen pixels (ADR-081, ADR-097 step 2): apart from the WebGL
// programs that draw it, so a test can read it without a WebGL context.

/** An unresolved link's dot: DESIGN.md v0.3 §3.8's `1 3`, doubled like the dash. */
export const DOT_LENGTH_PX = 2;
export const DOT_PERIOD_PX = 8;
/** An inferred link's dash: DESIGN.md v0.3 §3.8's `4 3`, doubled so the gap survives the canvas's
 * rasterising at one or two pixels wide (a short gap reads as a solid line on screen). */
export const DASH_LENGTH_PX = 8;
export const DASH_PERIOD_PX = 14;
