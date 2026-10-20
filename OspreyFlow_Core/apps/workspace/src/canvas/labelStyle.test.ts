import { describe, expect, it } from "vitest";
import { paletteFor } from "../color/palette";
import { fitToLength, hoverBoxFor, labelColoursFor, labelSide, nodeLabelLook } from "./labelStyle";

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
      expect(labelColoursFor(palette)).toEqual({ labelColor: palette.textPrimary, edgeLabelColor: palette.textPrimary });
      expect(nodeLabelLook(palette, "Petrenko", false).labelColor).toBe(palette.textPrimary);
    }
  });

  it("can be read against the canvas of each theme (WCAG AA, 4.5:1)", () => {
    for (const theme of ["dark", "light"] as const) {
      const palette = paletteFor(theme);
      expect(contrast(labelColoursFor(palette).labelColor, palette.surfaceSunken)).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("the box behind a hovered node's label", () => {
  for (const theme of ["dark", "light"] as const) {
    it(`is a ${theme} surface the theme's text can be read on`, () => {
      const palette = paletteFor(theme);
      const box = hoverBoxFor(palette);
      expect(box.backdropColor).toBe(palette.surfaceRaised);
      expect(contrast(palette.textPrimary, box.backdropColor)).toBeGreaterThanOrEqual(4.5);
    });
  }
});

describe("a node's label (ADR-097 step 2)", () => {
  it("is cut in the middle over 28 characters, in mono for a literal value, at 11px (DESIGN.md v0.3 §5a)", () => {
    const look = nodeLabelLook(paletteFor("dark"), "jeffrey.holloway@enron.example.com", true);
    expect(Array.from(look.label)).toHaveLength(24);
    expect(look.labelSize).toBe(11);
    expect(look.labelFont).toContain("IBM Plex Mono");
  });

  it("is a name in the UI face", () => {
    expect(nodeLabelLook(paletteFor("dark"), "Volkov, Anna", false).labelFont).toContain("Atkinson");
  });

  it("goes on the left of a node by the right-hand edge, and on the right elsewhere", () => {
    expect(labelSide({ x: 390, size: 10, textWidth: 84, canvasWidth: 400 })).toBe("left");
    expect(labelSide({ x: 100, size: 10, textWidth: 84, canvasWidth: 400 })).toBe("right");
    expect(nodeLabelLook(paletteFor("dark"), "Volkov, Anna", false, { x: 390, size: 10, canvasWidth: 400 }).labelPosition).toBe(
      "left",
    );
  });

  it("is empty when the node has none", () => {
    expect(nodeLabelLook(paletteFor("dark"), null, false).label).toBe("");
  });
});

describe("a link's label, cut to its link (as Sigma 3 drew it)", () => {
  const measure = (text: string) => Array.from(text).length * 7;
  it("is whole when it fits", () => {
    expect(fitToLength("Uses · 1 record", 200, measure)).toBe("Uses · 1 record");
  });
  it("is cut with an ellipsis to the room there is", () => {
    const cut = fitToLength("Uses · 1 record", 30, measure);
    expect(cut).toBe("Use…");
    expect(measure(cut)).toBeLessThanOrEqual(30);
  });
  it("is nothing, not a lone ellipsis, where not even a letter and the ellipsis fit", () => {
    expect(fitToLength("Uses · 1 record", 10, measure)).toBe("");
  });
});
