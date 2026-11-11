// Chromium's own shadow paint against the judgement's bracket (the orchestrator's review of T3b at
// 9697ad3, minor 1). Run through `node a11y/plants/run.mjs`, on the platform that gates (the test
// server): the judgement takes a shadow's alpha at a point to lie between `shadowCoverageRange`'s least
// and most, and this measures every pixel round a black shadow on white, for a straight edge at several
// blurs, an offset shadow and two rounded ones, and fails where Chromium paints outside the bracket.
// Its log gives, per band of σ past the shape, the most Chromium paints under the Gaussian of half
// the blur (away from rounded corners), the figure `SHADOW_SHORT` is set from.
import { createRequire } from "node:module";

import { expect, test } from "@playwright/test";

import { shadowCoverageRange } from "../../src/color/textContrast";

const { PNG } = createRequire(import.meta.url)("playwright-core/lib/utilsBundle") as {
  PNG: { sync: { read(b: Buffer): { width: number; height: number; data: Buffer } } };
};

const erf = (x: number) => {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const e = 1 - ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return x >= 0 ? e : -e;
};
const cdf = (z: number) => (1 + erf(z / Math.SQRT2)) / 2;

const GEOMETRIES = [
  ...[4, 8, 16, 24, 40].map((blur) => ({ name: `straight, blur ${blur}, spread ${blur}`, dx: 0, dy: 0, blur, spread: blur, radius: 0 })),
  { name: "offset 12, 8, blur 16", dx: 12, dy: 8, blur: 16, spread: 0, radius: 0 },
  { name: "rounded 16, blur 16", dx: 0, dy: 0, blur: 16, spread: 0, radius: 16 },
  { name: "rounded 8, blur 24, spread 4", dx: 0, dy: 0, blur: 24, spread: 4, radius: 8 },
];
const BANDS = [-3, -2, -1, 0, 1, 2, 3];

test("Chromium's shadow paint lies inside the judgement's bracket at every pixel", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 700 });
  const lines: string[] = [];
  for (const g of GEOMETRIES) {
    const box = { left: 200, top: 150, right: 600, bottom: 450 };
    await page.setContent(
      `<body style="margin:0;background:#fff"><div style="position:absolute;left:${box.left}px;top:${box.top}px;width:${box.right - box.left}px;height:${box.bottom - box.top}px;background:#fff;border-radius:${g.radius}px;box-shadow:${g.dx}px ${g.dy}px ${g.blur}px ${g.spread}px rgb(0, 0, 0)"></div></body>`,
    );
    const png = PNG.sync.read(await page.screenshot());
    const edges: [number, number, number, number] = [box.left + g.dx - g.spread, box.top + g.dy - g.spread, box.right + g.dx + g.spread, box.bottom + g.dy + g.spread];
    const [left, top, right, bottom] = edges;
    const sigma = g.blur / 2;
    const under = BANDS.map(() => 0); // the most measured falls below the Gaussian, away from corners
    const over = BANDS.map(() => -Infinity); // the most measured exceeds the bracket's most
    let belowLeast = 0;
    let worstAt = "";
    for (let py = 0; py < png.height; py += 1) {
      for (let px = 0; px < png.width; px += 1) {
        const [x, y] = [px + 0.5, py + 0.5];
        // The element paints over its own shadow; its edge's anti-aliased pixel is left out too.
        if (x > box.left - 1 && x < box.right + 1 && y > box.top - 1 && y < box.bottom + 1) continue;
        const measured = 1 - (png.data[(py * png.width + px) * 4] ?? 255) / 255;
        const radius = g.radius > 0 ? g.radius + Math.max(0, g.spread) : 0;
        const [least, most] = shadowCoverageRange({ colour: "rgb(0, 0, 0)", edges, blur: g.blur, radius, x, y });
        const past = Math.max(left - x, x - right, top - y, y - bottom);
        const band = BANDS.indexOf(Math.max(-3, Math.floor(past / sigma)));
        const reach = radius + 1.5 * g.blur;
        const nearCorner = radius > 0 && (x < left + reach || x > right - reach) && (y < top + reach || y > bottom - reach);
        const across = (v: number, lo: number, hi: number) => cdf((hi - v) / sigma) - cdf((lo - v) / sigma);
        const gauss = Math.max(0, across(x, left, right)) * Math.max(0, across(y, top, bottom));
        if (band >= 0) {
          if (!nearCorner) under[band] = Math.max(under[band] as number, gauss - measured);
          over[band] = Math.max(over[band] as number, measured - most);
        }
        // Within one 8-bit step of the bracket: the screenshot rounds each channel.
        const step = 0.5 / 255;
        if (measured < least - step || measured > most + step) {
          const off = Math.max(least - measured, measured - most);
          if (off > belowLeast) [belowLeast, worstAt] = [off, `(${x}, ${y}) measured ${measured.toFixed(4)} bracket [${least.toFixed(4)}, ${most.toFixed(4)}]`];
        }
      }
    }
    lines.push(
      `${g.name}: ${BANDS.map((k, b) => `[${k}σ,${k + 1}σ) under≤${(under[b] as number).toFixed(4)} over-most≤${(over[b] as number).toFixed(4)}`).join("; ")}` +
        (worstAt ? `\n    OUTSIDE the bracket by ${belowLeast.toFixed(4)} at ${worstAt}` : ""),
    );
    expect.soft(worstAt, `${g.name}: Chromium paints outside the bracket`).toBe("");
  }
  console.log(lines.join("\n"));
});
