// How a link is drawn (ADR-081, ADR-097 step 2), in Sigma 4's terms. Sigma 3 drew each line style
// with a program of its own, so the Glass carried dotted and dashed shaders of its own
// (`dottedEdgePrograms.ts`, retired with Sigma 3). Sigma 4 draws every link with one program built
// from layers, and its own `layerDashed` draws a pattern in screen pixels, so a link's style is now
// a handful of values the edge reducer hands that program:
//
// - `plainColor`: the solid line under everything. A patterned link leaves it transparent, so only
//   its dashes are drawn.
// - `dashLength` and `dashGap`: the pattern, as multiples of the line's width. Either at 0 draws no
//   pattern at all (Sigma's own rule), which is what a solid link is. Sigma 3's shaders kept the
//   pattern a fixed size on screen at every zoom; Sigma 4's pattern scales with the line, as the
//   line's own width already did, so the multiples are the Sigma 3 pattern's pixels at the
//   narrowest patterned width (`provenancePatterns.ts`), and the pattern's shape — DESIGN.md
//   §3.8's 1 3 and 4 3 — is the same at every zoom.
// - `head`: Sigma's own arrowhead, only for a type the ontology declares directed.
// - `size`: how wide it is drawn. Sigma 3's plain line program drew a pixel whatever the size; its
//   other programs moved each side of the line out by the size, at least 1.7 (`minEdgeThickness`),
//   so drew it twice as wide, and the arrowhead, a multiple of the width, with it. Sigma 4's size is
//   the whole width, so the same widths are twice the size here.
//
// The program itself is `GlassCanvas.tsx`'s `glassPrimitives`. The arrowhead of a patterned link is
// drawn whole (`solidExtremities`), as the v3 programs drew it.
import type { EdgeProgramName } from "./nodeAttributes";
import { DASH_LENGTH_PX, DASH_PERIOD_PX, DOT_LENGTH_PX, DOT_PERIOD_PX } from "./provenancePatterns";

/** Sigma's own arrowhead is short and narrow beside a 20px node (ADR-097 step 2): six times the
 * line's width long and five times as wide, as it was under Sigma 3. */
export const ARROW_HEAD = { lengthRatio: 6, widthRatio: 5 } as const;

const TRANSPARENT = "rgba(0, 0, 0, 0)";

/** The narrowest size a link other than a plain line is drawn at: Sigma 3's `minEdgeThickness`. */
export const MIN_PATTERNED_SIZE = 1.7;
/** The width that size was drawn at under Sigma 3, and the width the pattern's pixels were set at. */
export const PATTERN_BASE_WIDTH = 2 * MIN_PATTERNED_SIZE;

export interface LinkLook {
  plainColor: string;
  dashLength: number;
  dashGap: number;
  head: "arrow" | undefined;
  size: number;
}

/** The values a link of this style is drawn with: `program` is what `edgeProgramFor` chose, and
 * `color` and `size` the link's colour and width. */
export function linkLookFor(program: EdgeProgramName, color: string, size: number): LinkLook {
  const head = program.startsWith("glass-arrow") ? "arrow" : undefined;
  const width = program === "glass-edge" ? 1 : 2 * Math.max(size, MIN_PATTERNED_SIZE);
  const pattern = (on: number, period: number) => ({
    dashLength: on / PATTERN_BASE_WIDTH,
    dashGap: (period - on) / PATTERN_BASE_WIDTH,
  });
  if (program.endsWith("-dotted")) {
    return { plainColor: TRANSPARENT, ...pattern(DOT_LENGTH_PX, DOT_PERIOD_PX), head, size: width };
  }
  if (program.endsWith("-dashed")) {
    return { plainColor: TRANSPARENT, ...pattern(DASH_LENGTH_PX, DASH_PERIOD_PX), head, size: width };
  }
  return { plainColor: color, dashLength: 0, dashGap: 0, head, size: width };
}
