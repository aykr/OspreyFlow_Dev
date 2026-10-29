// The map view's camera across a resize, in a real browser (WebGL). Found preparing the Prison
// Intelligence demo, 29 October 2026: with located nodes drawn, opening the timeline (which shrinks
// the map's box) moved the camera to latitude -85, the edge of the projection, and the map went
// blank until another view was opened (ADR-086 Amendment 1).
import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 1100, height: 800 } });

async function centre(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const map = window.__MAP__;
    if (!map || !map.loaded()) return null;
    const c = map.getCenter();
    return { lat: c.lat, lng: c.lng };
  });
}

test("shrinking the map's box keeps the camera on the drawn nodes", async ({ page }) => {
  await page.goto("/keyboard/map-view-harness.html");
  await expect.poll(() => centre(page), { timeout: 20_000 }).not.toBeNull();
  // Settled on the yards first.
  await expect.poll(async () => (await centre(page))?.lat ?? 0, { timeout: 10_000 }).toBeGreaterThan(51.42);
  await page.getByRole("button", { name: "Shrink the map" }).click();
  await page.waitForTimeout(1500);
  const after = (await centre(page))!;
  expect(after.lat).toBeGreaterThan(51.42);
  expect(after.lat).toBeLessThan(51.44);
  expect(after.lng).toBeGreaterThan(-1.16);
  expect(after.lng).toBeLessThan(-1.14);
});

test("shrinking the map's box keeps every drawn node in view", async ({ page }) => {
  // After the fix above, the camera stayed on the nodes but stepped in by about one zoom level, so
  // two of the PID's three yards left the view when the timeline opened (29 October 2026).
  await page.goto("/keyboard/map-view-harness.html");
  await expect.poll(async () => (await centre(page))?.lat ?? 0, { timeout: 20_000 }).toBeGreaterThan(51.42);
  await page.waitForTimeout(1000);
  await page.getByRole("button", { name: "Shrink the map" }).click();
  await page.waitForTimeout(1500);
  const outside = await page.evaluate(() => {
    const map = window.__MAP__!;
    const yards = [
      { lat: 51.4309, lng: -1.1503 },
      { lat: 51.4305, lng: -1.1478 },
      { lat: 51.4296, lng: -1.1489 },
    ];
    const bounds = map.getBounds();
    return yards.filter((y) => !bounds.contains([y.lng, y.lat]));
  });
  expect(outside).toEqual([]);
});

