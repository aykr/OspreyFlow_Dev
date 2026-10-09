// 9 October 2026, the data engineer's journey: in the light theme, the entity picked as a link's
// start vanished from the Map canvas. It was painted the dark theme's primary text colour
// (#e8eced) on the light canvas (#f7fbfc); the canvas used dark-only constants, not the themed
// palette (ADR-070) the Glass canvas uses. Every colour this canvas paints must stand out from the
// canvas it is painted on, in either theme.
import { describe, expect, it } from "vitest";

import { oklabLightness } from "../../color/oklab";
import { paletteFor } from "../../color/palette";
import { mapCanvasColours, mapNodeColour } from "./mapCanvasColours";

const VISUAL = { channel: "ochre" };

describe.each(["light", "dark"] as const)("the Map canvas in the %s theme", (theme) => {
  const palette = paletteFor(theme);
  const background = oklabLightness(palette.surfaceApp);
  const standsOut = (hex: string) => Math.abs(oklabLightness(hex) - background) >= 0.2;

  it.each([
    ["an entity", { selected: false, linkFrom: false, visual: VISUAL }],
    ["the selected entity", { selected: true, linkFrom: false, visual: VISUAL }],
    ["the link's chosen start", { selected: false, linkFrom: true, visual: VISUAL }],
    ["an entity of a type the ontology does not know", { selected: false, linkFrom: false }],
  ])("draws %s so it can be seen", (_name, state) => {
    expect(standsOut(mapNodeColour(state, palette))).toBe(true);
  });

  it("draws its labels and links so they can be seen", () => {
    const colours = mapCanvasColours(palette);
    expect(standsOut(colours.label)).toBe(true);
    expect(standsOut(colours.edge)).toBe(true);
  });
});
