import { describe, expect, it } from "vitest";

import { cachedNodeSvgDataUri, renderNodeSvg } from "./nodeVisual";

const SHAPES = ["circle", "square", "diamond", "hexagon", "triangle", "page", "pin"] as const;

describe("renderNodeSvg", () => {
  it.each(SHAPES)("produces well-formed, non-empty SVG markup for %s", (shape) => {
    const svg = renderNodeSvg({
      shape,
      fillHex: "#677bd6",
      strokeHex: "#66696a",
      strokeStyle: "solid",
    });
    expect(svg).toMatch(/^<svg xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
    expect(svg).toContain('fill="#677bd6"');
    expect(svg).toContain('stroke="#66696a"');
    expect(svg.endsWith("</svg>")).toBe(true);
  });

  it.each(SHAPES)(
    "declares explicit width/height matching the viewBox for %s (regression)",
    (shape) => {
      // Without these, a plain `<img>` loading this data URI (no CSS/DOM
      // sizing context — exactly `@sigma/node-image`'s texture-atlas
      // loading path) falls back to a guessed intrinsic size and
      // rasterises the viewBox content into a corner of it rather than
      // scaling to fill — the shape becomes invisible once the atlas
      // crops tightly around that guessed size. Found by tracing the
      // real atlas pixel/UV pipeline in a browser, not from reading the
      // SVG spec — worth pinning down so it cannot silently regress.
      const svg = renderNodeSvg({
        shape,
        fillHex: "#000",
        strokeHex: "#fff",
        strokeStyle: "solid",
      });
      expect(svg).toMatch(/<svg[^>]*\swidth="32"/);
      expect(svg).toMatch(/<svg[^>]*\sheight="32"/);
    },
  );

  it("asserted (solid) carries no stroke-dasharray", () => {
    const svg = renderNodeSvg({
      shape: "circle",
      fillHex: "#000",
      strokeHex: "#fff",
      strokeStyle: "solid",
    });
    expect(svg).not.toContain("stroke-dasharray");
  });

  it("inferred is dashed 4 3 (DESIGN.md v0.3 §3.8)", () => {
    const svg = renderNodeSvg({
      shape: "circle",
      fillHex: "#000",
      strokeHex: "#fff",
      strokeStyle: "dashed",
    });
    expect(svg).toContain('stroke-dasharray="4 3"');
  });

  it("unresolved is dotted, distinct from dashed", () => {
    const svg = renderNodeSvg({
      shape: "circle",
      fillHex: "#000",
      strokeHex: "#fff",
      strokeStyle: "dotted",
    });
    // DESIGN.md v0.3 §3.8 and §5a: unresolved is `1 3`.
    expect(svg).toContain('stroke-dasharray="1 3"');
  });
});

describe("cachedNodeSvgDataUri", () => {
  it("returns a data URI and reuses the cache for identical specs", () => {
    const spec = {
      shape: "hexagon" as const,
      fillHex: "#35b9c0",
      strokeHex: "#66696a",
      strokeStyle: "solid" as const,
    };
    const first = cachedNodeSvgDataUri(spec);
    const second = cachedNodeSvgDataUri(spec);

    expect(first).toMatch(/^data:image\/svg\+xml/);
    expect(first).toBe(second);
  });

  it("produces a different URI for a different shape", () => {
    const a = cachedNodeSvgDataUri({
      shape: "circle",
      fillHex: "#000",
      strokeHex: "#fff",
      strokeStyle: "solid",
    });
    const b = cachedNodeSvgDataUri({
      shape: "square",
      fillHex: "#000",
      strokeHex: "#fff",
      strokeStyle: "solid",
    });
    expect(a).not.toBe(b);
  });
});
