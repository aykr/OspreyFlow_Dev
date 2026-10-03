import { describe, expect, it } from "vitest";

import { cachedNodeSvgDataUri, renderNodeSvg, type NodeShape, type NodeVisualSpec } from "./nodeVisual";

// ADR-079: a node's icon is drawn inside its shape, in the same generated picture, so the shape and
// the colour still carry the type and the icon adds to them.

const base: NodeVisualSpec = {
  shape: "circle",
  fillHex: "#5367cb",
  strokeHex: "#66696a",
  strokeStyle: "solid",
};
const DATA = "data:image/png;base64,iVBORw0KGgo=";

describe("a glyph icon", () => {
  const svg = renderNodeSvg({ ...base, icon: { kind: "glyph", name: "person", colourHex: "#ffffff" } });

  it("is drawn after the shape, in the colour given, inside the 32-unit picture", () => {
    expect(svg.indexOf("<circle")).toBeLessThan(svg.indexOf("<g "));
    expect(svg).toContain("#ffffff");
    const scale = svg.match(/<g transform="translate\(([\d.-]+) ([\d.-]+)\) scale\(([\d.]+)\)"/);
    expect(scale).not.toBeNull();
    const [x, y, k] = scale!.slice(1).map(Number) as [number, number, number];
    expect(x).toBeGreaterThanOrEqual(0);
    expect(y).toBeGreaterThanOrEqual(0);
    expect(x + 24 * k).toBeLessThanOrEqual(32);
    expect(y + 24 * k).toBeLessThanOrEqual(32);
  });

  it("keeps the shape's own outline, fill and provenance stroke", () => {
    expect(svg).toContain('fill="#5367cb"');
    expect(svg).toContain('stroke="#66696a"');
  });

  it("stays inside every shape's own outline", () => {
    // The glyph's box must lie within what each shape can hold: a triangle and a pin are narrow.
    const limit: Record<NodeShape, number> = {
      circle: 20,
      square: 20,
      diamond: 14,
      hexagon: 20,
      triangle: 12,
      page: 16,
      pin: 12,
    };
    for (const shape of Object.keys(limit) as NodeShape[]) {
      const out = renderNodeSvg({ ...base, shape, icon: { kind: "glyph", name: "person", colourHex: "#fff" } });
      const k = Number(out.match(/scale\(([\d.]+)\)/)![1]);
      expect(24 * k).toBeLessThanOrEqual(limit[shape]);
      expect(24 * k).toBeGreaterThan(6);
    }
  });

  it("is dimmed along with the node", () => {
    const dim = renderNodeSvg({
      ...base,
      icon: { kind: "glyph", name: "person", colourHex: "#ffffff" },
      iconOpacity: 0.4,
    });
    expect(dim).toContain('opacity="0.4"');
    expect(svg).not.toContain("opacity=");
  });

  it("draws nothing extra for a name that is not a drawing", () => {
    expect(
      renderNodeSvg({ ...base, icon: { kind: "glyph", name: "not-an-icon", colourHex: "#ffffff" } }),
    ).toBe(renderNodeSvg(base));
  });
});

describe("an image icon", () => {
  const svg = renderNodeSvg({ ...base, icon: { kind: "image", key: "image:1", dataUrl: DATA } });

  it("fills the shape and is cut to its outline, with the outline drawn over it", () => {
    expect(svg).toContain("<clipPath");
    expect(svg).toContain(`href="${DATA}"`);
    expect(svg).toContain('preserveAspectRatio="xMidYMid slice"');
    expect(svg).toContain("clip-path=");
    // The outline (no fill, the provenance stroke) comes last, so a dashed edge is still seen.
    expect(svg.lastIndexOf('fill="none"')).toBeGreaterThan(svg.indexOf("<image"));
  });

  it("refuses anything that is not a small raster picture given as a data address", () => {
    for (const bad of [
      "https://example.test/a.png",
      "javascript:alert(1)",
      "data:image/svg+xml;utf8,<svg/>",
      `${DATA}"/><script>`,
      'data:image/png;base64,AAA" onload="x',
    ]) {
      expect(renderNodeSvg({ ...base, icon: { kind: "image", key: "image:2", dataUrl: bad } })).toBe(
        renderNodeSvg(base),
      );
    }
  });
});

describe("the picture cache", () => {
  it("gives one picture for the same shape, fill, stroke and icon, and another when the icon differs", () => {
    const person = { kind: "glyph", name: "person", colourHex: "#ffffff" } as const;
    const a = cachedNodeSvgDataUri({ ...base, icon: person });
    expect(cachedNodeSvgDataUri({ ...base, icon: person })).toBe(a);
    expect(cachedNodeSvgDataUri({ ...base, icon: { ...person, name: "pin" } })).not.toBe(a);
    expect(cachedNodeSvgDataUri(base)).not.toBe(a);
    expect(cachedNodeSvgDataUri({ ...base, icon: person, iconOpacity: 0.4 })).not.toBe(a);
  });

  it("keys an image by its key, never by its (long) text, so the key must change when the picture does", () => {
    const other = "data:image/png;base64,AAAA";
    const one = cachedNodeSvgDataUri({ ...base, icon: { kind: "image", key: "image:7", dataUrl: DATA } });
    expect(cachedNodeSvgDataUri({ ...base, icon: { kind: "image", key: "image:7", dataUrl: other } })).toBe(one);
    expect(cachedNodeSvgDataUri({ ...base, icon: { kind: "image", key: "image:8", dataUrl: other } })).not.toBe(one);
  });
});
