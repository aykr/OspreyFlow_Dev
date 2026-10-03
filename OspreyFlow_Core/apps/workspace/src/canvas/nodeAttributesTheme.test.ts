// @vitest-environment jsdom
//
// The graph follows the light or dark theme (ADR-070): node fills, rings, the colour a dimmed node
// fades towards, and link colours come from the palette of the theme the page is showing.
import { afterEach, describe, expect, it } from "vitest";

import { paletteFor } from "../color/palette";
import { makeEdge, makeNode } from "../testing/fixtures";
import { applyTheme } from "../theme/theme";
import { computeClusterGraphAttributes, computeEdgeAttributes, computeNodeGraphAttributes } from "./nodeAttributes";

afterEach(() => applyTheme("dark"));

const VISUAL = { channel: "indigo", shape: "circle" } as const;
const STATE = { dimmed: false, filteredOut: false, hovered: false, selected: false, onPath: false };

describe("the graph in the light theme", () => {
  it("fills a node with its light channel colour, and the dark one in the dark theme", () => {
    applyTheme("dark");
    expect(computeNodeGraphAttributes(makeNode("n1"), VISUAL, STATE).color).toBe(paletteFor("dark").channel("indigo"));
    applyTheme("light");
    expect(computeNodeGraphAttributes(makeNode("n1"), VISUAL, STATE).color).toBe(paletteFor("light").channel("indigo"));
  });

  it("fades a dimmed node towards the light panel, not the dark one", () => {
    applyTheme("light");
    const dimmed = computeNodeGraphAttributes(makeNode("n1"), VISUAL, { ...STATE, dimmed: true }).color;
    const full = computeNodeGraphAttributes(makeNode("n1"), VISUAL, STATE).color;
    expect(dimmed).not.toBe(full);
    // Fading towards a near-white panel makes the fill lighter, not darker.
    const lightness = (hex: string) => parseInt(hex.slice(1, 3), 16) + parseInt(hex.slice(3, 5), 16) + parseInt(hex.slice(5, 7), 16);
    expect(lightness(dimmed)).toBeGreaterThan(lightness(full));
  });

  it("rings an on-path node in the theme's own text colour", () => {
    applyTheme("light");
    expect(computeNodeGraphAttributes(makeNode("n1"), VISUAL, { ...STATE, onPath: true }).borderColor).toBe(
      paletteFor("light").textPrimary,
    );
  });

  it("draws links and the cluster ring in the theme's own greys", () => {
    applyTheme("light");
    const edge = makeEdge("e1", "a", "b", { weight: 1 });
    const attrs = computeEdgeAttributes(edge, { cameraRatio: 0.3, strengthFilterFloor: 0, onPath: false });
    expect(attrs.color).toBe(paletteFor("light").borderStrong);
    expect(computeClusterGraphAttributes(3).clusterBorderColor).toBe(paletteFor("light").borderSubtle);
  });
});
