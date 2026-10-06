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
