// A selected node is seen (owner, 4 October 2026: "the nodes do not get highlighted when I select
// them"). Its 2-pixel brass ring was drawn inside a node a few pixels wide and could not be seen, so
// the DOM saying "selected" proved nothing; this reads the painted pixels around the node instead.
import { expect, test, type Page } from "@playwright/test";

import { readPng } from "./pngPixels";

declare global {
  interface Window {
    __KEYBOARD__?: { focused: string | null; selection: string[] };
    __CANVAS__?: { viewportPositionOf: (nodeId: string) => { x: number; y: number } | null };
  }
}

const BRASS: [number, number, number] = [0xc0, 0x8a, 0x34];

/** How many pixels within 14 of `nodeId`'s centre are within a small distance of brass. */
async function brassAround(page: Page, nodeId: string): Promise<number> {
  await page.waitForTimeout(400); // the next frame, with the new rings
  const canvas = page.getByRole("application", { name: "Network canvas" });
  const box = await canvas.boundingBox();
  const at = await page.evaluate((id) => window.__CANVAS__?.viewportPositionOf(id) ?? null, nodeId);
  if (!box || !at) throw new Error("the node is not drawn");
  const pixels = readPng(await page.screenshot());
  const scale = pixels.width / (page.viewportSize()?.width ?? pixels.width);
  const cx = Math.round((box.x + at.x) * scale);
  const cy = Math.round((box.y + at.y) * scale);
  const reach = Math.round(14 * scale);
  let count = 0;
  for (let y = cy - reach; y <= cy + reach; y++) {
    for (let x = cx - reach; x <= cx + reach; x++) {
      if (x < 0 || y < 0 || x >= pixels.width || y >= pixels.height) continue;
      const [r, g, b] = pixels.at(x, y);
      if (Math.abs(r - BRASS[0]) + Math.abs(g - BRASS[1]) + Math.abs(b - BRASS[2]) < 60) count++;
    }
  }
  return count;
}

test("a selected node shows a brass ring that can be seen, and loses it when deselected", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual(["n0"]);
  const selected = await brassAround(page, "n0");
  expect(selected).toBeGreaterThan(40);

  await page.keyboard.press(" "); // Space takes the focused node out of the selection
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selection)).toEqual([]);
  expect(await brassAround(page, "n0")).toBeLessThan(5);
});
