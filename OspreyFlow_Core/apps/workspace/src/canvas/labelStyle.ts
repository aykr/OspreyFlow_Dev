// How the graph's labels are coloured, by theme (ADR-070).
//
// Sigma paints a label in black unless it is told otherwise, and the box it draws behind the label
// of the node under the pointer is white. On the dark canvas that left every label unreadable. The
// graph is painted by a canvas that cannot read the page's CSS variables, so the colours come from
// the palette (`color/palette.ts`) and are pushed into Sigma's settings, again when the theme changes.
import type { NodeHoverDrawingFunction, NodeLabelDrawingFunction } from "sigma/rendering";
import type { Palette } from "../color/palette";
import { labelStartX, middleTruncate, NODE_LABEL_FONT, NODE_LABEL_MONO_FONT, NODE_LABEL_SIZE } from "./nodeLabel";

export interface LabelColours {
  labelColor: { color: string };
  edgeLabelColor: { color: string };
}

/** The colour of a node's label and of a link's label: the theme's primary text. */
export function labelColoursFor(palette: Palette): LabelColours {
  return {
    labelColor: { color: palette.textPrimary },
    edgeLabelColor: { color: palette.textPrimary },
  };
}

/** The label as drawn: over 28 characters, its first 19 and last 4 (DESIGN.md v0.3 §5a). */
function drawnText(data: { label?: string | null }): string {
  return typeof data.label === "string" ? middleTruncate(data.label) : "";
}

/** The font for a label: mono for a literal value (`labelLiteral`, set by the canvas's reducer). */
function fontFor(data: object, weight: string): string {
  const literal = (data as { labelLiteral?: boolean }).labelLiteral === true;
  return `${weight} ${NODE_LABEL_SIZE}px ${literal ? NODE_LABEL_MONO_FONT : NODE_LABEL_FONT}`;
}

/** The canvas's width in CSS pixels, the space Sigma draws labels in. */
function cssWidth(context: CanvasRenderingContext2D): number {
  const canvas = context.canvas as HTMLCanvasElement;
  return canvas.clientWidth || canvas.width / (globalThis.devicePixelRatio || 1);
}

/** Draws a node's label at `--fs-11` in the theme's text colour, in mono for a literal value, cut
 * in the middle over 28 characters, and on the left of the node when the right would leave the canvas. */
export function drawNodeLabel(palette: Palette): NodeLabelDrawingFunction {
  return (context, data, settings) => {
    const text = drawnText(data);
    if (text === "") return;
    context.font = fontFor(data, settings.labelWeight);
    context.fillStyle = palette.textPrimary;
    const x = labelStartX({
      x: data.x,
      size: data.size,
      textWidth: context.measureText(text).width,
      canvasWidth: cssWidth(context),
    });
    context.fillText(text, x, data.y + NODE_LABEL_SIZE / 3);
  };
}

/** Draws the node under the pointer: a raised surface of the theme behind the label (or a disc
 * where there is none), then the label in the theme's text colour. It is Sigma's own hover shape
 * with the white and the black taken out. */
export function drawHoveredNode(palette: Palette): NodeHoverDrawingFunction {
  return (context, data, settings) => {
    const size = NODE_LABEL_SIZE;
    context.font = fontFor(data, settings.labelWeight);
    const label = drawnText(data);

    context.fillStyle = palette.surfaceRaised;
    context.shadowOffsetX = 0;
    context.shadowOffsetY = 0;
    context.shadowBlur = 8;
    context.shadowColor = palette.surfaceSunken;
    const PADDING = 2;
    if (label !== "") {
      const textWidth = context.measureText(label).width;
      const boxWidth = Math.round(textWidth + 5);
      const boxHeight = Math.round(size + 2 * PADDING);
      const radius = Math.max(data.size, size / 2) + PADDING;
      const angle = Math.asin(boxHeight / 2 / radius);
      const dx = Math.sqrt(Math.abs(radius * radius - (boxHeight / 2) * (boxHeight / 2)));
      context.beginPath();
      context.moveTo(data.x + dx, data.y + boxHeight / 2);
      context.lineTo(data.x + radius + boxWidth, data.y + boxHeight / 2);
      context.lineTo(data.x + radius + boxWidth, data.y - boxHeight / 2);
      context.lineTo(data.x + dx, data.y - boxHeight / 2);
      context.arc(data.x, data.y, radius, angle, -angle);
      context.closePath();
      context.fill();
    } else {
      context.beginPath();
      context.arc(data.x, data.y, data.size + PADDING, 0, Math.PI * 2);
      context.closePath();
      context.fill();
    }
    context.shadowOffsetX = 0;
    context.shadowOffsetY = 0;
    context.shadowBlur = 0;

    if (label !== "") {
      context.fillStyle = palette.textPrimary;
      context.fillText(label, data.x + data.size + 3, data.y + size / 3);
    }
  };
}
