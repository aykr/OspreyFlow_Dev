// The undecided-contrast judgement's boundaries (rules-b's T3; the orchestrator's review, item 4):
// each branch shown with the strings Chrome produces, so a wrong threshold, a dropped gradient stop
// or an ignored overlap fails here, not only a 1:1 plant in a browser.
import { describe, expect, it } from "vitest";

import {
  excuses,
  gradientColours,
  judge,
  needFor,
  parseColour,
  ratioOf,
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
    expect(gradientColours(grid)).toHaveLength(4);
  });

  it("measures the text on a gradient's darkest stop, so a stop the colour of the text fails", () => {
    const on = (image: string) =>
      judge(sample({ color: "rgb(0, 0, 0)", chain: [layer({ backgroundColor: WHITE, backgroundImage: image })] }));
    expect(on("linear-gradient(rgb(250, 250, 250) 1px, rgba(0, 0, 0, 0) 1px)").why).toBe("");
    expect(on("linear-gradient(oklab(0 0 0) 1px, rgba(0, 0, 0, 0) 1px)").why).toMatch(/^1\.00:1/);
  });

  it("fails a stop it cannot read, and a picture, rather than dropping them", () => {
    expect(gradientColours("linear-gradient(lab(50 0 0), transparent)")).toBeNull();
    expect(gradientColours('url("tile.png")')).toBeNull();
    const pictured = judge(sample({ chain: [layer({ backgroundColor: WHITE, backgroundImage: "url(a.png)" })] }));
    expect(pictured.ratio).toBeNull();
    expect(pictured.why).toMatch(/picture or unread gradient/);
  });
});

describe("what lies under the text", () => {
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

  it("excuses an unmeasurable one only while it gives the same reason", () => {
    const over = judge(sample({ overlappedBy: "canvas.maplibregl-canvas" }));
    const listed = { text: "Words", ratio: "unmeasurable" as const, reason: "over or under canvas", owner: "platform" };
    expect(excuses(listed, over)).toBe(true);
    expect(excuses(listed, judge(sample({ chain: [layer({ filter: "blur(1px)" })] })))).toBe(false);
    expect(excuses(listed, found)).toBe(false);
  });
});
