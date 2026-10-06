// Selecting a link with the mouse (ADR-064). A drawn link is a one- or two-pixel line, which the
// renderer's own picking rarely hits, so a click within a few pixels of one must still select it,
// and a click well away from every link must not. This is the browser proof of that: the unit test
// (`src/canvas/edgeSelection.test.ts`) checks the arithmetic, this checks it is wired to a real
// canvas. Not a keyboard test, so it sits outside the `CANVAS_ACTIONS` registry.
import { expect, test, type Page } from "@playwright/test";

import { layoutSettled } from "./layoutSettled";
import { readPng } from "./pngPixels";

declare global {
  interface Window {
    __KEYBOARD__?: { selectedEdge: string | null; selection: string[] };
    __CANVAS__?: { viewportPositionOf: (nodeId: string) => { x: number; y: number } | null };
  }
}

async function settledPositions(page: Page, a: string, b: string) {
  const at = await layoutSettled(page, [a, b]);
  return { a: at[a]!, b: at[b]! };
}

async function clickBeside(page: Page, offset: number) {
  const { a, b } = await settledPositions(page, "n0", "n1");
  const box = await page.getByRole("application", { name: "Network canvas" }).boundingBox();
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const length = Math.hypot(b.x - a.x, b.y - a.y);
  const normal = { x: -(b.y - a.y) / length, y: (b.x - a.x) / length };
  await page.mouse.click(box!.x + mid.x + normal.x * offset, box!.y + mid.y + normal.y * offset);
}

test("a click a few pixels off a link selects it", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await clickBeside(page, 4);
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBe("e0");
});

test("a click on the link itself selects it", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await clickBeside(page, 0);
  await expect.poll(() => page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBe("e0");
});

test("a click well away from every link selects nothing", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await clickBeside(page, 16);
  await page.waitForTimeout(400);
  expect(await page.evaluate(() => window.__KEYBOARD__?.selectedEdge)).toBeNull();
});

// Seen 3 October 2026: Clear view "did not work" for the owner. The buttons were drawn, but the
// renderer's canvas layers sat on top of them, so a mouse click never reached them. The keyboard
// tests could not see it: Enter on a focused button never goes through hit-testing. Playwright's
// own `click()` refuses to click an element something else covers, which is the check needed here.
test("the buttons over the canvas can be clicked with the mouse", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  let removed: { node_ids: string[] } | null = null;
  await page.route("**/*/investigations/*/nodes", async (route) => {
    removed = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ seq: 9 }) });
  });

  await page.getByRole("button", { name: "Clear view" }).click({ timeout: 3000 });
  await expect(page.getByRole("alertdialog", { name: "Clear the view" })).toBeVisible();
  await page.getByRole("button", { name: /^Clear all/ }).click({ timeout: 3000 });
  await expect.poll(() => removed?.node_ids.length).toBe(6);

  await page.getByRole("combobox", { name: "Layout" }).selectOption("circular", { timeout: 3000 });
  await expect(page.getByRole("combobox", { name: "Layout" })).toHaveValue("circular");
  await page.getByRole("button", { name: "Arrange again" }).click({ timeout: 3000 });
});

test("the large-expansion prompt's buttons can be clicked with the mouse", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  let expandBody: unknown = null;
  await page.route("**/*/expand/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ candidate_node_count: 1200, candidate_edge_count: 0 }),
    });
  });
  await page.route("**/*/expand", async (route) => {
    expandBody = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] }, filtered_count: 0 }),
    });
  });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alertdialog", { name: "Large expansion" })).toBeVisible();
  await page.getByRole("button", { name: /^Add all/ }).click({ timeout: 3000 });
  await expect.poll(() => expandBody).not.toBeNull();
});

// Seen 3 October 2026 on the Fixture Corp hub: after a search drew the nodes the links were not
// there, and appeared only once the owner clicked the empty canvas. The renderer leaves links out
// while the camera is moving (`hideEdgesOnMove`), and the last frame of the camera's settling move
// was drawn before it counted as finished, so nothing drew the links afterwards. The DOM cannot say
// whether a WebGL line was painted, so this reads the pixels along the link between two nodes.
test("the links are drawn once the layout has settled, without a click on the canvas", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  // The layout moves the nodes for about a second and then the camera for a little under half of
  // one, so wait it out in full and only then read where the nodes are.
  await page.waitForTimeout(2500);
  const { a, b } = await settledPositions(page, "n0", "n1");
  const box = (await page.getByRole("application", { name: "Network canvas" }).boundingBox())!;
  const pixels = readPng(await page.screenshot());
  const background = pixels.at(Math.round(box.x) + 20, Math.round(box.y) + 300);
  let drawn = 0;
  let sampled = 0;
  for (let i = 15; i <= 85; i++) {
    const t = i / 100;
    const x = Math.round(box.x + a.x + (b.x - a.x) * t);
    const y = Math.round(box.y + a.y + (b.y - a.y) * t);
    let strongest = 0;
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const p = pixels.at(x + dx, y + dy);
        strongest = Math.max(strongest, Math.abs(p[0] - background[0]) + Math.abs(p[1] - background[1]) + Math.abs(p[2] - background[2]));
      }
    }
    sampled += 1;
    if (strongest > 40) drawn += 1;
  }
  expect(drawn / sampled).toBeGreaterThan(0.9);
});

// Seen 3 October 2026 (owner, screenshot): in the dark theme the node labels were unreadable. Sigma
// paints a label in black unless told otherwise, and the graph never told it. The labels are drawn
// on their own 2D canvas, so their pixels can be read: the text drawn there must be light on the
// dark theme, not black.
test("node labels are drawn in a light colour on the dark theme", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await settledPositions(page, "n0", "n1");
  await page.waitForTimeout(500);
  const ink = await page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>("canvas.sigma-labels");
    if (!canvas) return null;
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let drawn = 0;
    let brightness = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3]! < 200) continue; // only the solid middle of a letter, not its soft edge
      drawn += 1;
      brightness += (data[i]! + data[i + 1]! + data[i + 2]!) / 3;
    }
    return { drawn, mean: drawn ? brightness / drawn : 0 };
  });
  expect(ink, "the label canvas exists").not.toBeNull();
  expect(ink!.drawn, "some label text is drawn").toBeGreaterThan(20);
  expect(ink!.mean, "and it is light, not black").toBeGreaterThan(180);
});
