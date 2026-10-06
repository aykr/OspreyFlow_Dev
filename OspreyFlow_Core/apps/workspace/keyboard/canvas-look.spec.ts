// What the canvas paints, read from the pixels (ADR-097 step 2, design review item 9). A node's size
// is a number handed to Sigma; this checks the number becomes 20 painted pixels across at 100%.
import { expect, test, type Page } from "@playwright/test";

import { readPng } from "./pngPixels";

declare global {
  interface Window {
    __CANVAS__?: {
      viewportPositionOf: (nodeId: string) => { x: number; y: number } | null;
      zoomTo: (ratio: number) => void;
    };
  }
}

/** The painted width of `nodeId` along a row and down a column through its centre, in CSS pixels:
 * the run of pixels that differ from the canvas behind it. The smaller of the two, since a link
 * leaving the node lengthens the run along its own direction. */
async function paintedDiameter(page: Page, nodeId: string): Promise<number> {
  const canvas = page.getByRole("application", { name: "Network canvas" });
  const box = (await canvas.boundingBox())!;
  const at = await page.evaluate((id) => window.__CANVAS__?.viewportPositionOf(id) ?? null, nodeId);
  if (!at) throw new Error("the node is not drawn");
  const pixels = readPng(await page.screenshot());
  const scale = pixels.width / page.viewportSize()!.width;
  const cx = Math.round((box.x + at.x) * scale);
  const cy = Math.round((box.y + at.y) * scale);
  const near = (a: number[], b: number[]) => Math.abs(a[0]! - b[0]!) + Math.abs(a[1]! - b[1]!) + Math.abs(a[2]! - b[2]!) < 24;
  const run = (dx: number, dy: number) => {
    const background = pixels.at(cx + dx * Math.round(40 * scale), cy + dy * Math.round(40 * scale));
    let out = 0;
    while (out < 60 * scale && !near(pixels.at(cx + dx * out, cy + dy * out), background)) out++;
    return out;
  };
  const across = run(1, 0) + run(-1, 0);
  const down = run(0, 1) + run(0, -1);
  return Math.min(across, down) / scale;
}

test("a node is 20 pixels across at 100%", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.viewportPositionOf("n3") ?? null)).not.toBeNull();
  await page.evaluate(() => window.__CANVAS__?.zoomTo(1));
  await page.waitForTimeout(400);
  const diameter = await paintedDiameter(page, "n3");
  expect(diameter).toBeGreaterThanOrEqual(18);
  expect(diameter).toBeLessThanOrEqual(23);
});

test("the canvas shows its 8px measurement grid behind the graph", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await page.waitForTimeout(600);
  const box = (await page.getByRole("application", { name: "Network canvas" }).boundingBox())!;
  const pixels = readPng(await page.screenshot());
  const scale = pixels.width / page.viewportSize()!.width;
  // A strip of empty canvas below the top-left controls: find a row inside the cells (the vertical
  // lines only), then the columns that differ from that row's commonest colour.
  const x0 = Math.round((box.x + 200) * scale);
  let found: number[] = [];
  for (let dy = 0; dy < 8 && found.length === 0; dy++) {
    const y = Math.round((box.y + 140 + dy) * scale);
    const row = Array.from({ length: Math.round(64 * scale) }, (_, i) => pixels.at(x0 + i, y));
    const key = (p: number[]) => p.slice(0, 3).join(",");
    const counts = new Map<string, number>();
    for (const p of row) counts.set(key(p), (counts.get(key(p)) ?? 0) + 1);
    const commonest = [...counts].sort((a, b) => b[1] - a[1])[0]![0];
    const lines = row.map((p, i) => (key(p) === commonest ? -1 : i)).filter((i) => i >= 0);
    if (lines.length >= 6 && lines.length <= 10) found = lines;
  }
  expect(found.length).toBeGreaterThanOrEqual(6);
  const gaps = found.slice(1).map((x, i) => (x - found[i]!) / scale);
  for (const gap of gaps) expect(gap).toBeCloseTo(8, 0);
});

test("the canvas's tools are one docked toolbar of labelled groups, with Show as one segmented control and no shadows", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/harness.html");
  const toolbar = page.getByRole("toolbar", { name: "Canvas tools" });
  await expect(toolbar).toBeVisible();
  for (const name of ["Select", "Layout", "Show", "View"]) {
    await expect(toolbar.getByRole("group", { name })).toBeVisible();
  }
  const show = toolbar.getByRole("group", { name: "Show" });
  await expect(show).toHaveClass(/segmented/);
  await expect(show.getByRole("button", { name: "Communities" })).toBeVisible();
  await expect(show.getByRole("button", { name: /^Labels/ })).toBeVisible();
  await expect(show.getByRole("button", { name: /^Icons/ })).toBeVisible();
  // One row: every group's top within a few pixels of the first's.
  const tops = await toolbar.getByRole("group").evaluateAll((els) => els.map((el) => el.getBoundingClientRect().top));
  for (const top of tops) expect(Math.abs(top - tops[0]!)).toBeLessThan(4);
  // Docked, so a hairline and no shadow (DESIGN.md §6), on the bar and every control in it. (A pressed
  // segment's underline is an inset stroke, not a shadow.)
  const shadows = await toolbar.evaluate((bar) =>
    [bar, ...Array.from(bar.querySelectorAll("button, select"))].map((el) => getComputedStyle(el).boxShadow),
  );
  expect(shadows.filter((s) => s !== "none" && !s.includes("inset"))).toEqual([]);
});
