import { expect, test } from "@playwright/test";

import { readPng } from "../keyboard/pngPixels";

declare global {
  interface Window {
    __captureChartExport__?: (mark: {
      osprey_mark: "OspreyFlow";
      investigation_id: string;
      exported_at: string;
      resolution_threshold: number;
      handling_level: string;
    }) => Promise<{ bytes: number[]; width: number; height: number }>;
  }
}

// Proves `captureChartImage` (`src/export/chartExport.ts`) against a real, WebGL-rendered `Sigma`
// instance — `apps/workspace/export-capture/harness.tsx`'s own module docstring has the full
// "why this needs a real browser, not vitest" reasoning. A15 (`spec/08_ACCEPTANCE_SCENARIOS.md`)
// now asserts the export "produces a real artefact of the requested shape... carrying the mark" —
// this is the one part of that assertion, for the chart shape, that no vitest test in this
// repository can reach, so it is proven here instead of left unproven.

const MARK = {
  osprey_mark: "OspreyFlow" as const,
  investigation_id: "export-capture-fixture",
  exported_at: "2026-09-23T00:00:00Z",
  resolution_threshold: 0.95,
  handling_level: "OFFICIAL",
};

test("chart export captures a real, non-blank rendering of the populated canvas, carrying the mark", async ({
  page,
}) => {
  await page.goto("/export-capture/harness.html");
  await page.waitForFunction(() => typeof window.__captureChartExport__ === "function");
  // Sigma's own first frame; give the WebGL renderer a moment to actually paint before capturing —
  // capturing on the very first tick would risk a genuinely blank canvas for a reason that has
  // nothing to do with the code under test.
  await page.waitForTimeout(500);

  const result = await page.evaluate(async (mark) => {
    const capture = window.__captureChartExport__;
    if (!capture) throw new Error("harness did not expose __captureChartExport__");
    const { bytes, width, height } = await capture(mark);

    // The mark, as `embedPngTextChunks`/`chartMarkFields` actually wrote it — decoded from the
    // real captured bytes, not asserted against bytes the test itself supplied.
    const asText = String.fromCharCode(...bytes);
    const markFieldsPresent = {
      osprey_mark: asText.includes(`osprey_mark\0${mark.osprey_mark}`),
      investigation_id: asText.includes(`investigation_id\0${mark.investigation_id}`),
      handling_level: asText.includes(`handling_level\0${mark.handling_level}`),
    };

    // Real, non-trivial pixel content: decode the captured PNG as an image and read its own
    // pixels back — proving the *underlying capture*, not only the mark appended to it, actually
    // shows the rendered canvas (several distinct node/edge colours, not a single flat fill a
    // blank canvas would also produce).
    const blob = new Blob([new Uint8Array(bytes)], { type: "image/png" });
    const bitmap = await createImageBitmap(blob);
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("no 2D context available to decode the captured PNG");
    ctx.drawImage(bitmap, 0, 0);
    const { data } = ctx.getImageData(0, 0, bitmap.width, bitmap.height);

    const distinctColours = new Set<string>();
    let nonBackgroundPixelCount = 0;
    // Sample every 7th pixel (prime stride, avoids any accidental periodicity in the render) —
    // cheap enough to run on the full frame without the test itself becoming the slow part.
    for (let i = 0; i < data.length; i += 4 * 7) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      distinctColours.add(`${r},${g},${b}`);
    }
    const first = [data[0], data[1], data[2]] as const;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] !== first[0] || data[i + 1] !== first[1] || data[i + 2] !== first[2]) {
        nonBackgroundPixelCount++;
      }
    }

    return {
      byteLength: bytes.length,
      width,
      height,
      markFieldsPresent,
      distinctColourCount: distinctColours.size,
      nonBackgroundPixelCount,
    };
  }, MARK);

  // The artefact is a real image of the harness's own canvas size, not an empty or placeholder
  // byte string.
  expect(result.width).toBeGreaterThan(100);
  expect(result.height).toBeGreaterThan(100);
  expect(result.byteLength).toBeGreaterThan(1000);

  // The mark is present in the real captured bytes.
  expect(result.markFieldsPresent.osprey_mark).toBe(true);
  expect(result.markFieldsPresent.investigation_id).toBe(true);
  expect(result.markFieldsPresent.handling_level).toBe(true);

  // Real content, not a blank fill: several distinct colours (background + at least two node
  // channels + edges + the watermark text), and a meaningful number of pixels that differ from
  // whatever the very first pixel happens to be (the background, on any real render).
  expect(result.distinctColourCount).toBeGreaterThan(5);
  expect(result.nonBackgroundPixelCount).toBeGreaterThan(500);
});

// ADR-118: under Sigma 4 the Glass's look — pictures, rings, line patterns, label colours — is its
// reducers', and a second renderer built from the first's primitives, styles and settings alone
// (`@sigma/export-image`'s way) draws none of it. So what is exported must be what is on screen:
// every fully drawn pixel of the export is the colour of the same pixel of the canvas.
test("chart export is the canvas as it is drawn", async ({ page }) => {
  await page.goto("/export-capture/harness.html");
  await page.waitForFunction(() => typeof window.__captureChartExport__ === "function");
  await page.waitForTimeout(1500);
  const exported = await page.evaluate(async (mark) => {
    const { bytes } = await window.__captureChartExport__!(mark);
    const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: "image/png" }));
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(bitmap, 0, 0);
    const stage = [...document.querySelectorAll("canvas")].sort((a, b) => b.width * b.height - a.width * a.height)[0]!;
    const rect = stage.getBoundingClientRect();
    return {
      width: bitmap.width,
      height: bitmap.height,
      data: Array.from(ctx.getImageData(0, 0, bitmap.width, bitmap.height).data),
      at: { x: rect.x, y: rect.y, width: rect.width },
    };
  }, MARK);
  const screen = readPng(await page.screenshot());
  const scale = exported.width / exported.at.width;
  let compared = 0;
  let alike = 0;
  // The watermark is drawn on the export only: its bottom 30 pixels are left out.
  for (let y = 0; y < exported.height - 30 * scale; y++) {
    for (let x = 0; x < exported.width; x++) {
      const i = (y * exported.width + x) * 4;
      if (exported.data[i + 3]! < 250) continue; // only what the canvas fully drew
      const p = screen.at(Math.round(exported.at.x + x / scale), Math.round(exported.at.y + y / scale));
      compared += 1;
      const d =
        Math.abs(p[0]! - exported.data[i]!) + Math.abs(p[1]! - exported.data[i + 1]!) + Math.abs(p[2]! - exported.data[i + 2]!);
      if (d < 40) alike += 1;
    }
  }
  expect(compared, "the export draws something").toBeGreaterThan(200);
  expect(alike / compared, "and it is what the canvas shows").toBeGreaterThan(0.9);
});
