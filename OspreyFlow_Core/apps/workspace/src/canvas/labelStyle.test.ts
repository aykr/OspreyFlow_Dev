import { describe, expect, it } from "vitest";
import { paletteFor } from "../color/palette";
import { drawHoveredNode, drawNodeLabel, labelColoursFor } from "./labelStyle";

// Sigma paints a label in black unless it is told otherwise, which is invisible on the dark canvas.
// These tests pin that the label colours come from the theme's palette and that the box drawn
// behind a hovered node's label is a surface of that theme, so the text on it can be read.

/** The relative luminance of a "#rrggbb" colour (WCAG 2). */
function luminance(hex: string): number {
  const channel = (start: number): number => {
    const c = parseInt(hex.slice(start, start + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

describe("label colours", () => {
  it("are the theme's primary text colour, for node labels and link labels", () => {
    for (const theme of ["dark", "light"] as const) {
      const palette = paletteFor(theme);
      const colours = labelColoursFor(palette);
      expect(colours.labelColor).toEqual({ color: palette.textPrimary });
      expect(colours.edgeLabelColor).toEqual({ color: palette.textPrimary });
    }
  });

  it("can be read against the canvas of each theme (WCAG AA, 4.5:1)", () => {
    for (const theme of ["dark", "light"] as const) {
      const palette = paletteFor(theme);
      const colours = labelColoursFor(palette);
      expect(contrast(colours.labelColor.color, palette.surfaceSunken)).toBeGreaterThanOrEqual(4.5);
    }
  });
});

/** A canvas context that records the colour in force at each fill and each piece of text. */
function recordingContext() {
  const fills: string[] = [];
  const texts: { text: string; colour: string }[] = [];
  const context = {
    fillStyle: "",
    font: "",
    shadowOffsetX: 0,
    shadowOffsetY: 0,
    shadowBlur: 0,
    shadowColor: "",
    measureText: (text: string) => ({ width: text.length * 6 }),
    beginPath: () => undefined,
    moveTo: () => undefined,
    lineTo: () => undefined,
    arc: () => undefined,
    closePath: () => undefined,
    fill() {
      fills.push(this.fillStyle);
    },
    fillText(text: string) {
      texts.push({ text, colour: this.fillStyle });
    },
  };
  return { context, fills, texts };
}

const SETTINGS = {
  labelSize: 12,
  labelFont: "sans-serif",
  labelWeight: "normal",
} as never;

describe("the box behind a hovered node's label", () => {
  for (const theme of ["dark", "light"] as const) {
    it(`is a ${theme} surface with the theme's text on it, readable`, () => {
      const palette = paletteFor(theme);
      const { context, fills, texts } = recordingContext();
      drawHoveredNode(palette)(
        context as unknown as CanvasRenderingContext2D,
        { x: 50, y: 50, size: 6, label: "Petrenko", color: "#5367cb" } as never,
        SETTINGS,
      );
      expect(fills).toEqual([palette.surfaceRaised]);
      expect(texts).toEqual([{ text: "Petrenko", colour: palette.textPrimary }]);
      expect(contrast(palette.textPrimary, palette.surfaceRaised)).toBeGreaterThanOrEqual(4.5);
    });
  }

  it("is still drawn, as a plain disc, when the node has no label", () => {
    const palette = paletteFor("dark");
    const { context, fills, texts } = recordingContext();
    drawHoveredNode(palette)(
      context as unknown as CanvasRenderingContext2D,
      { x: 50, y: 50, size: 6, label: null, color: "#5367cb" } as never,
      SETTINGS,
    );
    expect(fills).toEqual([palette.surfaceRaised]);
    expect(texts).toEqual([]);
  });
});

describe("drawNodeLabel (ADR-097 step 2)", () => {
  function fakeContext(width: number) {
    const drawn: { text: string; x: number; font: string }[] = [];
    const context = {
      canvas: { clientWidth: width, width },
      font: "",
      fillStyle: "",
      measureText: (text: string) => ({ width: text.length * 7 }),
      fillText(text: string, x: number) {
        drawn.push({ text, x, font: this.font });
      },
    };
    return { context: context as unknown as CanvasRenderingContext2D, drawn };
  }
  const settings = { labelWeight: "normal" } as never;

  it("draws a long literal label cut in the middle, in mono, at 11px (DESIGN.md v0.3 §5a)", () => {
    const { context, drawn } = fakeContext(800);
    const draw = drawNodeLabel(paletteFor("dark"));
    draw(context, { x: 100, y: 100, size: 10, label: "jeffrey.holloway@enron.example.com", labelLiteral: true } as never, settings);
    expect(drawn).toHaveLength(1);
    expect(drawn[0]!.text).toHaveLength(24);
    expect(drawn[0]!.font).toContain("11px");
    expect(drawn[0]!.font).toContain("IBM Plex Mono");
  });

  it("draws a name in the UI face, and on the left of a node by the right-hand edge", () => {
    const { context, drawn } = fakeContext(400);
    drawNodeLabel(paletteFor("dark"))(context, { x: 390, y: 50, size: 10, label: "Volkov, Anna" } as never, settings);
    expect(drawn[0]!.font).toContain("Atkinson");
    expect(drawn[0]!.x + "Volkov, Anna".length * 7).toBeLessThanOrEqual(400);
  });
});
