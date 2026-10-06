// Dragging across the timeline's bars selects a window, and that window is what dims the graph
// (`02_GLASS_FRONTEND.md` §3.4: "drag to select a window"). Found by the owner, 6 October 2026: a
// drag across the bars did nothing, because it went to the chart's own pan-and-zoom, which has
// nothing to pan at full range; only the thin slider's end handles set a window. A pointer test, so
// it sits outside the keyboard registry; the keyboard route to a window is Set exact dates.
import { expect, test } from "@playwright/test";

const DAYS = 10;
const HISTOGRAM = {
  bucketing: "fixed_interval",
  buckets: Array.from({ length: DAYS }, (_, i) => ({
    start: new Date(Date.UTC(2026, 0, 1 + i)).toISOString(),
    end: new Date(Date.UTC(2026, 0, 2 + i)).toISOString(),
    count: 3 + (i % 4),
  })),
  total: 40,
};

test("dragging across the bars selects a window and asks which nodes and links fall in it", async ({ page }) => {
  const firstSeenWindows: unknown[] = [];
  await page.route("**/*/v1/analytics/histogram", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(HISTOGRAM) }),
  );
  await page.route("**/*/v1/analytics/first-seen", async (route) => {
    firstSeenWindows.push((route.request().postDataJSON() as { filter?: { window?: unknown } }).filter?.window);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ nodes: {}, edges: {} }) });
  });
  await page.goto("/keyboard/timeline-playback-harness.html?nowindow");
  const chart = page.locator("[data-timeline-tracks] canvas").first();
  await expect(chart).toBeVisible();
  const box = (await chart.boundingBox())!;
  const y = box.y + box.height * 0.4;
  await page.mouse.move(box.x + box.width * 0.3, y);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.45, y, { steps: 5 });
  await page.mouse.move(box.x + box.width * 0.6, y, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => page.evaluate(() => window.__TIMELINE_PLAYBACK_HARNESS__?.window ?? null)).not.toBeNull();
  const win = (await page.evaluate(() => window.__TIMELINE_PLAYBACK_HARNESS__!.window))!;
  // A part of the ten days, not all of them.
  expect(win.validFrom > HISTOGRAM.buckets[0]!.start).toBe(true);
  expect(win.validTo! < HISTOGRAM.buckets[DAYS - 1]!.end).toBe(true);
  await expect.poll(() => firstSeenWindows.length).toBeGreaterThan(0);
});
