// The Ingest Studio's row-template canvas, read from its pixels (spec 09 §4). 9 October 2026: with a
// link already in the template, picking the next link's start left only the picked entity drawn.
// None of these sequences reproduces that in isolation (each was shown able to fail, by a planted sync
// that drops every entity but the link's start); they guard the canvas while the live Studio is checked.
import { expect, test, type Page } from "@playwright/test";

import { readPng } from "./pngPixels";

/** How many painted pixels on the canvas differ from its bare background. */
async function paintedPixels(page: Page): Promise<number> {
  const hide = await page.addStyleTag({ content: "[data-harness-only] { visibility: hidden !important; }" });
  const canvas = page.getByRole("img", { name: "Row template canvas" });
  const box = (await canvas.boundingBox())!;
  const pixels = readPng(await page.screenshot());
  const scale = pixels.width / page.viewportSize()!.width;
  const background = pixels.at(Math.round((box.x + 2) * scale), Math.round((box.y + 2) * scale));
  let count = 0;
  for (let y = Math.round(box.y * scale); y < Math.round((box.y + box.height) * scale); y += 2) {
    for (let x = Math.round(box.x * scale); x < Math.round((box.x + box.width) * scale); x += 2) {
      const p = pixels.at(x, y);
      if (Math.abs(p[0]! - background[0]!) + Math.abs(p[1]! - background[1]!) + Math.abs(p[2]! - background[2]!) > 30) count++;
    }
  }
  await hide.evaluate((tag) => tag.remove());
  return count;
}

test("picking a link's start with a link already made leaves every entity drawn", async ({ page }) => {
  await page.goto("/keyboard/map-canvas-harness.html");
  await page.waitForTimeout(500);
  const before = await paintedPixels(page);
  expect(before).toBeGreaterThan(200);
  await page.getByRole("button", { name: "Pick handset as a link's start" }).click();
  await page.waitForTimeout(500);
  const after = await paintedPixels(page);
  expect(after).toBeGreaterThan(before * 0.8);
});

test("clicking a node to start a link, with a link already made, leaves every entity drawn", async ({ page }) => {
  await page.goto("/keyboard/map-canvas-harness.html?real=1");
  await page.waitForTimeout(500);
  const before = await paintedPixels(page);
  const canvas = page.getByRole("img", { name: "Row template canvas" });
  const box = (await canvas.boundingBox())!;
  const at = await page.evaluate(() => window.__MAP__?.positionOf("handset") ?? null);
  expect(at).not.toBeNull();
  await page.mouse.click(box.x + at!.x, box.y + at!.y);
  await page.mouse.move(box.x + 5, box.y + 5);
  await page.waitForTimeout(500);
  const after = await paintedPixels(page);
  expect(after).toBeGreaterThan(before * 0.8);
});

test("an entity added after a link, then clicked as the next link's start, leaves every entity drawn", async ({ page }) => {
  await page.goto("/keyboard/map-canvas-harness.html?real=1&later=1");
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Add handset" }).click();
  await page.waitForTimeout(500);
  const before = await paintedPixels(page);
  const canvas = page.getByRole("img", { name: "Row template canvas" });
  const box = (await canvas.boundingBox())!;
  const at = await page.evaluate(() => window.__MAP__?.positionOf("handset") ?? null);
  await page.mouse.click(box.x + at!.x, box.y + at!.y);
  await page.mouse.move(box.x + 5, box.y + 5);
  await page.waitForTimeout(500);
  const after = await paintedPixels(page);
  expect(after).toBeGreaterThan(before * 0.8);
});
