// How the graph's labels look, by theme (ADR-070).
//
// Sigma paints a label in black unless it is told otherwise, and the box it draws behind the node
// under the pointer is white. On the dark canvas that left every label unreadable. The graph is
// painted by WebGL, which cannot read the page's CSS variables, so the colours come from the palette
// (`color/palette.ts`); the canvas's reducers read them on every refresh, and a change of theme
// refreshes.
//
// Sigma 4 draws labels itself, on the GPU, from these values; Sigma 3 called a drawing function of
// the Glass's own (retired with it). What that function did is kept: `--fs-11`, mono for a literal
// value, cut in the middle over 28 characters (DESIGN.md v0.3 §5a), and on the left of the node when
// the right would run past the canvas's edge.
import type { Palette } from "../color/palette";
import { middleTruncate, NODE_LABEL_FONT, NODE_LABEL_MONO_FONT, NODE_LABEL_SIZE } from "./nodeLabel";

export interface LabelColours {
  labelColor: string;
  edgeLabelColor: string;
}

/** The colour of a node's label and of a link's label: the theme's primary text. */
export function labelColoursFor(palette: Palette): LabelColours {
  return { labelColor: palette.textPrimary, edgeLabelColor: palette.textPrimary };
}

/** The box behind the node under the pointer: a raised surface of the theme, lifted by a shadow of
 * its sunken surface, so the theme's text on it can be read. */
export function hoverBoxFor(palette: Palette) {
  return {
    backdropColor: palette.surfaceRaised,
    backdropShadowColor: palette.surfaceSunken,
    backdropShadowBlur: 8,
    backdropPadding: 2,
  };
}

/** Which side of its node a label goes: the right when it fits inside the canvas, else the left. */
export function labelSide(at: { x: number; size: number; textWidth: number; canvasWidth: number }): "right" | "left" {
  const GAP = 3;
  return at.x + at.size + GAP + at.textWidth <= at.canvasWidth ? "right" : "left";
}

let measuring: CanvasRenderingContext2D | null | undefined;

/** The width of `text` in `font` at `size` pixels, in CSS pixels; a rough one where there is no
 * canvas to measure on. */
export function textWidth(text: string, font: string, size: number = NODE_LABEL_SIZE): number {
  if (measuring === undefined) {
    try {
      measuring = document.createElement("canvas").getContext("2d");
    } catch {
      measuring = null;
    }
  }
  if (!measuring) return text.length * size * 0.6;
  measuring.font = `${size}px ${font}`;
  return measuring.measureText(text).width;
}

/** A node's label as drawn, its face, size, colour and side (`at` is where the node is on screen). */
export function nodeLabelLook(
  palette: Palette,
  label: string | null | undefined,
  literal: boolean,
  at?: { x: number; size: number; canvasWidth: number },
) {
  const text = typeof label === "string" ? middleTruncate(label) : "";
  const font = literal ? NODE_LABEL_MONO_FONT : NODE_LABEL_FONT;
  return {
    label: text,
    labelFont: font,
    labelSize: NODE_LABEL_SIZE,
    labelColor: palette.textPrimary,
    labelPosition:
      at && text !== "" ? labelSide({ ...at, textWidth: textWidth(text, font) }) : ("right" as const),
  };
}

/** A link's label as Sigma 3 drew it: Arial at 14px (its defaults, which the Glass never changed). */
export const LINK_LABEL_FONT = "Arial, sans-serif";
export const LINK_LABEL_SIZE = 14;

/** `text` cut with an ellipsis to fit `room` pixels, as Sigma 3 cut a link's label to its link;
 * empty when not even one character and the ellipsis fit. `measure` gives a string's width. */
export function fitToLength(text: string, room: number, measure: (text: string) => number): string {
  if (text === "" || measure(text) <= room) return text;
  const chars = Array.from(text);
  for (let keep = chars.length - 1; keep > 0; keep--) {
    const cut = `${chars.slice(0, keep).join("").trimEnd()}…`;
    if (measure(cut) <= room) return cut;
  }
  return "";
}
