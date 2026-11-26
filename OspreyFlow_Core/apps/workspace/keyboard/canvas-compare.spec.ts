// The canvas-look comparison (ADR-152 decision 9; ADR-002 Amendment 1, item 5; slice WS4a). WS4, the React
// workspace's move to Sigma 4, is held to it: each fixed scene (`canvas-compare-harness.tsx`) is drawn by the real
// canvas and its whole painted area compared against a reference image kept in `canvas-compare/`, within the one
// pixel tolerance in `canvas-compare/TOLERANCE.json` and never above `CEILING` (`canvasCompare.ts`). There is no list
// of accepted differences.
//
// The references are made only by `npm run canvas-compare:references -- --reason "…"`
// (`canvas-compare/make-references.mjs`), which records who made them, why, on which machine and from which commit in
// `canvas-compare/REFERENCES.json`; this spec refuses a reference that record does not bear out, and never writes one
// itself (unlike `toHaveScreenshot`, which writes a missing one and passes). Made on Sigma 3, they are what WS4b's port
// to Sigma 4 must still draw.
//
// Pixels differ between graphics stacks, so the references and the tolerance belong to one renderer: Chromium's
// software WebGL (SwiftShader), as on CI's hosted runners, at a device scale of 1. The tolerance was set from three
// runs of Sigma 3 against its own references (`TOLERANCE.json` records them and the machine).
import { readFileSync, writeFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { CEILING, FOLDER, compare, readReferences, toleranceRefusal, type Tolerance } from "./canvasCompare";
import { layoutSettled } from "./layoutSettled";

interface SceneCase {
  /** The reference's name (`canvas-compare/<name>.png`). */
  name: string;
  /** The harness's scene. */
  scene: string;
  /** A zoom after the fit (1 is 100%; above 1 is zoomed out). */
  zoom?: number;
  /** A node the pointer rests on (its hover drawing). */
  hover?: string;
  /** The canvas's exported PNG (`exportImage`, `chartExport.ts`) in place of a screenshot. */
  exported?: boolean;
}

export const CASES: readonly SceneCase[] = [
  { name: "links", scene: "links" },
  { name: "links-zoomed-out", scene: "links", zoom: 3 },
  { name: "nodes", scene: "nodes" },
  { name: "labels", scene: "labels" },
  { name: "hover", scene: "chain", hover: "c1" },
  { name: "selected-node", scene: "selected-node" },
  { name: "selected-link", scene: "selected-link" },
  { name: "export", scene: "chain", exported: true },
];

const WRITING = process.env.CANVAS_COMPARE_WRITE === "1";

test.use({ viewport: { width: 1000, height: 700 }, deviceScaleFactor: 1, reducedMotion: "reduce" });

// Everything the page draws over the canvas that is not the canvas's drawing: its controls and legend (the toolbar
// is not drawn at all, `toolbarHidden`). The grid behind the graph is the canvas's own and stays.
const CHROME = "button, select, label, .canvas-legend, .canvas-zoom, .selection-bar { visibility: hidden !important; }";

async function frames(page: Page, count = 3): Promise<void> {
  await page.evaluate(
    (n) =>
      new Promise<void>((resolve) => {
        const step = (left: number) => (left === 0 ? resolve() : requestAnimationFrame(() => step(left - 1)));
        step(n);
      }),
    count,
  );
}

/** Draws `c` and returns its picture as PNG bytes. */
async function draw(page: Page, c: SceneCase): Promise<Buffer> {
  await page.goto(`/keyboard/canvas-compare-harness.html?scene=${c.scene}`);
  await page.waitForFunction(() => window.__COMPARE__ !== undefined);
  expect(await page.evaluate(() => window.__COMPARE__!.facesLoaded), "the product's label face loaded").toBe(true);
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await expect(canvas).toHaveAttribute("data-canvas-state", "drawn");
  const ids = await page.evaluate(() => window.__COMPARE__!.nodeIds);
  await layoutSettled(page, ids);
  // The scene's own places, then the view fitted to them as a person fits it (F, the canvas focused).
  await page.evaluate(() => window.__COMPARE__!.pin());
  await canvas.focus();
  await page.keyboard.press("f");
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await layoutSettled(page, ids);
  const camera = await page.evaluate(() => window.__CANVAS__!.cameraState());
  expect(camera, "the view fitted to the scene").toEqual({ x: 0.5, y: 0.5, ratio: 1 });
  if (c.zoom) {
    await page.evaluate((ratio) => window.__CANVAS__!.zoomTo(ratio), c.zoom);
    await layoutSettled(page, ids);
  }
  await page.addStyleTag({ content: CHROME });
  const box = (await canvas.boundingBox())!;
  if (c.hover) {
    const at = await page.evaluate((id) => window.__CANVAS__!.viewportPositionOf(id), c.hover);
    await page.mouse.move(box.x + at!.x, box.y + at!.y);
  } else {
    await page.mouse.move(0, 0);
  }
  await page.waitForTimeout(400);
  await frames(page);
  if (c.exported) {
    const base64 = await page.evaluate(async () => {
      const blob = await window.__CANVAS__!.exportImage({
        osprey_mark: "OspreyFlow",
        investigation_id: "canvas-compare",
        exported_at: "2026-11-26T00:00:00Z",
        resolution_threshold: 0.95,
        handling_level: "OFFICIAL",
      });
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let text = "";
      for (const b of bytes) text += String.fromCharCode(b);
      return btoa(text);
    });
    return Buffer.from(base64, "base64");
  }
  return page.screenshot({ clip: box, animations: "disabled", caret: "hide" });
}

const tolerance = JSON.parse(readFileSync(new URL("TOLERANCE.json", FOLDER), "utf8")) as Tolerance & Record<string, unknown>;

test("the comparison's tolerance is within its ceiling", () => {
  expect(toleranceRefusal(tolerance), `ceiling: channel ${CEILING.channel}, share ${CEILING.share}`).toBeNull();
});

test("every reference is the one the reference-making command recorded", () => {
  test.skip(WRITING, "the references are being made");
  expect(readReferences(CASES.map((c) => c.name)).problems).toEqual([]);
});

for (const c of CASES) {
  test(`the canvas draws the ${c.name} scene as its reference does`, async ({ page }, info) => {
    const picture = await draw(page, c);
    const reference = new URL(`${c.name}.png`, FOLDER);
    if (WRITING) {
      // Only the command writes (it sets the reason); never in CI.
      expect(process.env.CANVAS_COMPARE_REASON?.trim(), "a reason, given to the command").toBeTruthy();
      expect(process.env.CI, "references are never made in CI").toBeFalsy();
      writeFileSync(reference, picture);
      return;
    }
    expect(toleranceRefusal(tolerance)).toBeNull();
    await info.attach(`${c.name}-actual.png`, { body: picture, contentType: "image/png" });
    const result = compare(picture, readFileSync(reference), tolerance.channel);
    console.log(`canvas-compare ${c.name}: ${result.differing} of ${result.width * result.height} pixels differ by more than ${tolerance.channel} (share ${result.share.toFixed(6)})`);
    expect(result.share, `the share of pixels unlike the reference (tolerance ${tolerance.share})`).toBeLessThanOrEqual(tolerance.share);
  });
}
