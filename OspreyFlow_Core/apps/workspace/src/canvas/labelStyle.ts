// How the graph's labels are coloured, by theme (ADR-070).
//
// Sigma paints a label in black unless it is told otherwise, and the box it draws behind the label
// of the node under the pointer is white. On the dark canvas that left every label unreadable. The
// graph is painted by a canvas that cannot read the page's CSS variables, so the colours come from
// the palette (`color/palette.ts`) and are pushed into Sigma's settings, again when the theme changes.
import type { NodeHoverDrawingFunction } from "sigma/rendering";
import type { Palette } from "../color/palette";

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

/** Draws the node under the pointer: a raised surface of the theme behind the label (or a disc
 * where there is none), then the label in the theme's text colour. It is Sigma's own hover shape
 * with the white and the black taken out. */
export function drawHoveredNode(palette: Palette): NodeHoverDrawingFunction {
  return (context, data, settings) => {
    const size = settings.labelSize;
    context.font = `${settings.labelWeight} ${size}px ${settings.labelFont}`;

    context.fillStyle = palette.surfaceRaised;
    context.shadowOffsetX = 0;
    context.shadowOffsetY = 0;
    context.shadowBlur = 8;
    context.shadowColor = palette.surfaceSunken;
    const PADDING = 2;
    if (typeof data.label === "string" && data.label !== "") {
      const textWidth = context.measureText(data.label).width;
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

    if (typeof data.label === "string" && data.label !== "") {
      context.fillStyle = palette.textPrimary;
      context.fillText(data.label, data.x + data.size + 3, data.y + size / 3);
    }
  };
}
