// The undecided-contrast judgement's boundaries (rules-b's T3; the orchestrator's review, item 4):
// each path shown with the strings Chrome produces, so a wrong threshold, a dropped gradient stop
// or an ignored overlap fails here, not only a 1:1 plant in a browser.
import { describe, expect, it } from "vitest";

import {
  excuses,
  gradientSurfaces,
  judge,
  needFor,
  parseColour,
  ratioOf,
  readFindings,
  type Layer,
  type Rgba,
  type Sample,
} from "./textContrast";

const WHITE = "rgb(255, 255, 255)";

/** A grey whose contrast with white is exactly `ratio`, as Chrome would write it. */
function greyAt(ratio: number): string {
  const lum = 1.05 / ratio - 0.05;
  const s = lum <= 0.0031308 ? 12.92 * lum : 1.055 * lum ** (1 / 2.4) - 0.055;
  const v = s * 255;
  return `rgb(${v}, ${v}, ${v})`;
}

function layer(more: Partial<Layer> = {}): Layer {
  return {
    name: "div",
    backgroundColor: "rgba(0, 0, 0, 0)",
    backgroundImage: "none",
    opacity: "1",
    filter: "none",
    backdropFilter: "none",
    mixBlendMode: "normal",
    paintedPseudo: null,
    covers: [true],
    ...more,
  };
}

function sample(more: Partial<Sample> = {}): Sample {
  return {
    selector: ".x",
    unreadable: null,
    text: "Words",
    color: greyAt(7),
    fontSize: "16px",
    fontWeight: "400",
    chain: [layer(), layer({ name: "body", backgroundColor: WHITE })],
    overlappedBy: null,
    axeReason: null,
    ...more,
  };
}

describe("the thresholds", () => {
  it("fails 4.49:1 at 16px and passes 4.51:1", () => {
    expect(judge(sample({ color: greyAt(4.49) })).why).toMatch(/^4\.49:1 < 4\.5:1/);
    expect(judge(sample({ color: greyAt(4.51) })).why).toBe("");
  });

  it("passes 3.01:1 at 24px and fails it at 23.9px", () => {
    expect(judge(sample({ color: greyAt(3.01), fontSize: "24px" })).why).toBe("");
    expect(judge(sample({ color: greyAt(3.01), fontSize: "23.9px" })).why).toMatch(/< 4\.5:1/);
  });

  it("passes 3.01:1 at 18.67px bold, fails it regular, and fails it bold just under 14pt", () => {
    expect(judge(sample({ color: greyAt(3.01), fontSize: "18.67px", fontWeight: "700" })).why).toBe("");
    expect(judge(sample({ color: greyAt(3.01), fontSize: "18.67px", fontWeight: "400" })).why).toMatch(/< 4\.5:1/);
    expect(needFor("18.66px", "700")).toBe(4.5);
    expect(needFor(`${(14 * 4) / 3}px`, "700")).toBe(3);
  });
});

describe("the colours Chrome writes", () => {
  it("reads rgb, rgba, space syntax, color(srgb), oklab, oklch and transparent", () => {
    expect(parseColour("rgb(10, 20, 30)")).toEqual([10, 20, 30, 1]);
    expect(parseColour("rgba(10, 20, 30, 0.5)")).toEqual([10, 20, 30, 0.5]);
    expect(parseColour("rgb(10 20 30 / 50%)")).toEqual([10, 20, 30, 0.5]);
    expect(parseColour("color(srgb 1 0 0 / 0.4)")).toEqual([255, 0, 0, 0.4]);
    expect(parseColour("transparent")).toEqual([0, 0, 0, 0]);
    const white = parseColour("oklab(1 0 0)") as Rgba;
    expect(white.map(Math.round)).toEqual([255, 255, 255, 1]);
    const red = parseColour("oklch(0.628 0.2577 29.23)") as Rgba;
    expect(red.slice(0, 3).map(Math.round)).toEqual([255, 0, 0]);
  });

  it("reads a `none` component or alpha as unread, never as NaN that passes", () => {
    for (const css of ["oklch(0.5 0 none)", "oklab(none 0 0)", "rgb(0 0 0 / none)", "color(srgb none 0 0)"]) {
      expect(parseColour(css), css).toBeNull();
    }
    const missing = judge(sample({ color: "oklch(0.5 0 none)" }));
    expect(missing.ratio).toBeNull();
    expect(missing.why).toMatch(/unread colour/);
    const underNone = judge(sample({ chain: [layer({ backgroundColor: "rgb(255 255 255 / none)" })] }));
    expect(underNone.why).toMatch(/unread background colour/);
  });

  it("reads a channel out of its range as unread, not as a colour", () => {
    // Chrome clamps an rgb() it computes, so its out-of-range shape is `color(srgb …)` (a color-mix or
    // relative colour past the gamut); rgb() and oklab() out of range stay refused as a second line.
    for (const css of ["color(srgb 4 0 0)", "color(srgb 0 -2 0 / 0.5)", "rgb(0 0 900)", "rgba(0, 0, 0, 2)", "oklab(3 0 0)"]) {
      expect(parseColour(css), css).toBeNull();
    }
    expect(parseColour("color(srgb 1.0001 -0.0001 0.5)")).toEqual([255, 0, 127.5, 1]);
  });

  it("reads nothing it does not know, so the caller fails it", () => {
    for (const css of ["lab(50 20 30)", "lch(50 20 30)", "color(display-p3 1 0 0)", "currentcolor", "hsl(0 0% 0%)"]) {
      expect(parseColour(css), css).toBeNull();
    }
  });
});

describe("gradients", () => {
  it("reads every stop of the canvas grid as Chrome computes color-mix in oklab", () => {
    const grid =
      "linear-gradient(oklab(0.4 0.01 0.02 / 0.4) 1px, rgba(0, 0, 0, 0) 1px), " +
      "linear-gradient(90deg, oklab(0.4 0.01 0.02 / 0.4) 1px, rgba(0, 0, 0, 0) 1px)";
    // Each layer: the colour beneath it (unpainted parts), its two stops and 7 between them = 10.
    expect(gradientSurfaces(grid, [255, 255, 255, 1])).toHaveLength(100);
  });

  it("measures the text on every stop, so a stop the colour of the text fails", () => {
    const on = (image: string) =>
      judge(sample({ color: "rgb(0, 0, 0)", chain: [layer({ backgroundColor: WHITE, backgroundImage: image })] }));
    expect(on("linear-gradient(rgb(250, 250, 250) 1px, rgba(0, 0, 0, 0) 1px)").why).toBe("");
    expect(on("linear-gradient(oklab(0 0 0) 1px, rgba(0, 0, 0, 0) 1px)").why).toMatch(/^1\.00:1/);
  });

  it("measures the colours between two stops, so a smooth gradient straddling the text fails", () => {
    // Black text: white and mid grey both pass 4.5:1, but the gradient passes through no darker
    // than grey; text in rgb(118) is 4.54:1 on white and ~1:1 midway on a white-to-black gradient.
    const text = "rgb(118, 118, 118)";
    const ends = judge(sample({ color: text, chain: [layer({ backgroundColor: WHITE })] }));
    expect(ends.why).toBe("");
    const smooth = judge(
      sample({
        color: text,
        chain: [layer({ backgroundColor: WHITE, backgroundImage: "linear-gradient(rgb(255, 255, 255), rgb(0, 0, 0))" })],
      }),
    );
    expect(smooth.ratio as number).toBeLessThan(1.2);
  });

  it("composites stacked layers where they cross, as the canvas grid's lines do", () => {
    const line = parseColour("rgba(0, 0, 0, 0.4)") as Rgba;
    const grid = "linear-gradient(rgba(0, 0, 0, 0.4) 1px, rgba(0, 0, 0, 0) 1px), linear-gradient(90deg, rgba(0, 0, 0, 0.4) 1px, rgba(0, 0, 0, 0) 1px)";
    const surfaces = gradientSurfaces(grid, [255, 255, 255, 1]) as Rgba[];
    // One line over white is 60% white; two crossing lines 36% white (64% covered).
    const darkest = Math.min(...surfaces.map((c) => c[0]));
    expect(line[3]).toBe(0.4);
    expect(darkest).toBeCloseTo(255 * 0.36, 3);
  });

  it("keeps the element's own background beneath an opaque stop, as a sized layer leaves it", () => {
    // background: #000 linear-gradient(#fff, #fff) 0 0 / 1px 1px no-repeat; color: #000.
    const sized = judge(
      sample({
        color: "rgb(0, 0, 0)",
        chain: [layer({ backgroundColor: "rgb(0, 0, 0)", backgroundImage: "linear-gradient(rgb(255, 255, 255), rgb(255, 255, 255))" })],
      }),
    );
    expect(sized.why).toMatch(/^1\.00:1/);
  });

  it("skips a `none` layer among gradients, and fails a spread too large to measure", () => {
    expect(gradientSurfaces("none, linear-gradient(rgb(0, 0, 0), rgb(0, 0, 0))", [255, 255, 255, 1])).not.toBeNull();
    const many = Array.from({ length: 4 }, () => "linear-gradient(rgb(0, 0, 0), rgb(255, 255, 255), rgb(0, 0, 0))").join(", ");
    expect(gradientSurfaces(many, [255, 255, 255, 1])).toBe("more than 20000 possible backgrounds");
    const spread = judge(sample({ chain: [layer({ backgroundColor: WHITE, backgroundImage: many })] }));
    expect(spread.why).toMatch(/not measurable: more than 20000 possible backgrounds on <div>/);
  });

  it("fails a stop it cannot read, and a picture, rather than dropping them", () => {
    expect(gradientSurfaces("linear-gradient(lab(50 0 0), transparent)", [255, 255, 255, 1])).toBe("an unread gradient");
    expect(gradientSurfaces('url("tile.png")', [255, 255, 255, 1])).toBe("a background picture");
    const pictured = judge(sample({ chain: [layer({ backgroundColor: WHITE, backgroundImage: "url(a.png)" })] }));
    expect(pictured.ratio).toBeNull();
    expect(pictured.why).toBe("not measurable: a background picture on <div>");
  });
});

describe("what lies under the text", () => {
  it("measures an SVG label's words on the shape under them, point by point", () => {
    // Show as BPMN's task: words in fill rgb(232, 236, 237) on a task box filled rgb(40, 44, 46), the
    // drawing's own element a white dialog; the second point is past the box, on the dialog.
    const label = (under: string[][]) =>
      judge(sample({ color: "rgb(232, 236, 237)", chain: [layer({ backgroundColor: WHITE })], under }));
    expect(label([["rgb(40, 44, 46)"]]).why).toBe("");
    expect(label([["rgb(40, 44, 46)"], []]).why).toMatch(/< 4\.5:1/);
    expect(label([["rgb(225, 229, 230)"]]).why).toMatch(/^1\.\d\d:1/);
    expect(label([["url(#hatch)"]]).why).toMatch(/unread shape fill/);
  });

  it("lays everything on the browser's own canvas, not on white", () => {
    const dark = "rgb(18, 18, 18)";
    // Light grey text on nothing but the canvas: fine on a dark canvas, 1.4:1 on white.
    const onCanvas = (page?: string) => judge(sample({ color: "rgb(220, 220, 220)", chain: [layer()], page }));
    expect(onCanvas(dark).why).toBe("");
    expect(onCanvas().why).toMatch(/< 4\.5:1/);
    expect(onCanvas("rgba(0, 0, 0, 0)").why).toMatch(/unread page colour/);
  });

  it("composites an alpha stack: 50% black over white under 50% white text", () => {
    const stacked = judge(
      sample({
        color: "rgba(255, 255, 255, 0.5)",
        chain: [layer({ backgroundColor: "rgba(0, 0, 0, 0.5)" }), layer({ name: "body", backgroundColor: WHITE })],
      }),
    );
    // bg = rgb(127.5) (lum ≈ 0.212); text = 0.5 white over it = rgb(191.25) (lum ≈ 0.521).
    expect(stacked.ratio).toBeCloseTo(ratioOf([191.25, 191.25, 191.25, 1], [127.5, 127.5, 127.5, 1]), 6);
    expect(stacked.why).toMatch(/< 4\.5:1/);
  });

  it("applies an ancestor's opacity to its whole group", () => {
    const black: Partial<Sample> = { color: "rgb(0, 0, 0)" };
    const solid = judge(sample({ ...black, chain: [layer({ backgroundColor: WHITE }), layer({ backgroundColor: "rgb(0, 0, 0)" })] }));
    const faded = judge(
      sample({ ...black, chain: [layer({ backgroundColor: WHITE, opacity: "0.3" }), layer({ backgroundColor: "rgb(0, 0, 0)" })] }),
    );
    expect(solid.why).toBe("");
    expect(faded.why).toMatch(/< 4\.5:1/);
  });

  it("measures a text axe calls partly covered on its own surfaces when the probe finds nothing", () => {
    // axe says this of text below the fold or past a scrolling box; the probe, with the text scrolled
    // into view and every element taking pointer events, decides what lies at its points.
    for (const axeReason of ["elmPartiallyObscured", "elmPartiallyObscuring"]) {
      expect(judge(sample({ axeReason, color: greyAt(7) })).why).toBe("");
      expect(judge(sample({ axeReason, color: greyAt(4.4) })).why).toMatch(/^4\.40:1 < 4\.5:1/);
      const covered = judge(sample({ axeReason, overlappedBy: "div.toast" }));
      expect(covered.ratio).toBeNull();
      expect(covered.why).toMatch(/over or under div\.toast/);
    }
  });

  it("measures a text that spills past its box on both surfaces, point by point", () => {
    // <div style="width:40px; white-space:nowrap; background:#222; color:#333">Account name</div> on white:
    // the first point is on the div, the others past it on the page.
    const spill = judge(
      sample({
        color: "rgb(51, 51, 51)",
        chain: [
          layer({ backgroundColor: "rgb(34, 34, 34)", covers: [true, false, false] }),
          layer({ backgroundColor: WHITE, covers: [true, true, true] }),
        ],
      }),
    );
    // #333 on #222 (1.26:1) counts, not #333 on the page past the box (12.6:1).
    expect(spill.ratio).toBeCloseTo(ratioOf([51, 51, 51, 1], [34, 34, 34, 1]), 6);
  });

  it("lays nothing under the text from an ancestor whose box is not under it", () => {
    // Black text inside a black box that does not reach the text, over a white page: measured on white.
    const outside = judge(
      sample({
        color: "rgb(0, 0, 0)",
        chain: [layer({ backgroundColor: "rgb(0, 0, 0)", covers: [false] }), layer({ backgroundColor: WHITE })],
      }),
    );
    expect(outside.why).toBe("");
    const inside = judge(
      sample({ color: "rgb(0, 0, 0)", chain: [layer({ backgroundColor: "rgb(0, 0, 0)" }), layer({ backgroundColor: WHITE })] }),
    );
    expect(inside.why).toMatch(/^1\.00:1/);
  });

  it("fails an overlapped node, a painted pseudo-element, a filter and a blend as unmeasurable", () => {
    const cases: [Partial<Sample>, RegExp][] = [
      [{ overlappedBy: "canvas.maplibregl-canvas", axeReason: "bgOverlap" }, /over or under canvas.*axe: bgOverlap/],
      [{ chain: [layer({ paintedPseudo: "::before" })] }, /painted ::before/],
      [{ chain: [layer({ filter: "blur(1px)" })] }, /filter or blend/],
      [{ chain: [layer({ backdropFilter: "blur(4px)" })] }, /filter or blend/],
      [{ chain: [layer({ mixBlendMode: "multiply" })] }, /filter or blend/],
      [{ unreadable: "a node in a shadow root" }, /shadow root/],
      [{ color: "currentcolor" }, /unread colour/],
      [{ chain: [layer({ backgroundColor: "lab(50 0 0)" })] }, /unread background colour/],
    ];
    for (const [more, why] of cases) {
      const j = judge(sample({ color: "rgb(0, 0, 0)", ...more }));
      expect(j.ratio, String(why)).toBeNull();
      expect(j.why).toMatch(why);
    }
  });
});

describe("a listed finding", () => {
  const found = judge(sample({ color: greyAt(2.85) }));

  it("excuses only its own text, at its ratio or better", () => {
    expect(excuses({ text: "Words", ratio: 2.85, owner: "platform" }, found)).toBe(true);
    expect(excuses({ text: "Words", ratio: 2.9, owner: "platform" }, found)).toBe(false);
    expect(excuses({ text: "Other words", ratio: 2.85, owner: "platform" }, found)).toBe(false);
    expect(excuses(undefined, found)).toBe(false);
  });

  it("excuses an unmeasurable one only while it gives exactly the same reason", () => {
    const over = judge(sample({ overlappedBy: "canvas.maplibregl-canvas", axeReason: "imgNode" }));
    const listed = {
      text: "Words",
      ratio: "unmeasurable" as const,
      reason: "over or under canvas.maplibregl-canvas",
      own: 7,
      owner: "platform",
    };
    expect(excuses(listed, over)).toBe(true);
    // Pinned to its own surfaces too: the same reason with its colours fallen is not excused.
    const fallen = judge(sample({ overlappedBy: "canvas.maplibregl-canvas", color: greyAt(2) }));
    expect(excuses(listed, fallen)).toBe(false);
    expect(excuses({ ...listed, own: null }, over)).toBe(false);
    expect(excuses({ ...listed, reason: "over or under canvas" }, over)).toBe(false);
    expect(excuses(listed, judge(sample({ overlappedBy: "canvas.other" })))).toBe(false);
    expect(excuses(listed, judge(sample({ chain: [layer({ filter: "blur(1px)" })] })))).toBe(false);
    expect(excuses(listed, found)).toBe(false);
  });
});

describe("the findings file", () => {
  const good = {
    "a.html (dark)": {
      ".x": { text: "Words", ratio: 3.2, owner: "case" },
      ".y": { text: "More", ratio: "unmeasurable", reason: "over or under div", own: 7.1, owner: "shell" },
    },
  };

  it("reads a well-formed file as it is", () => {
    expect(readFindings(good)).toEqual(good);
  });

  it("refuses a malformed entry, naming it", () => {
    const broken = (entry: unknown) => ({ "a.html (dark)": { ".x": entry } });
    const cases: [unknown, RegExp][] = [
      [[], /the file: not an object of looks/],
      [{ "a.html (dark)": [] }, /a\.html \(dark\): not an object of selectors/],
      [broken({ text: "W", ratio: "unmeasurable", own: 2, owner: "o" }), /› \.x: unexpected fields/],
      [broken({ text: "W", ratio: "unmeasurable", reason: "", own: 2, owner: "o" }), /no reason/],
      [broken({ text: "W", ratio: 3, owner: "o", own: 2 }), /unexpected fields/],
      [broken({ text: "W", ratio: 40, owner: "o" }), /ratio out of range/],
      [broken({ text: "W", ratio: "bad", owner: "o" }), /neither a number/],
      [broken({ ratio: 3, owner: "o" }), /no text or owner/],
      [broken({ text: "W", ratio: "unmeasurable", reason: "r", own: "7", owner: "o" }), /own ratio out of range/],
    ];
    for (const [json, why] of cases) expect(() => readFindings(json), String(why)).toThrow(why);
  });
});
