// The map view's camera across a resize, in a real browser (WebGL). Found preparing the Prison
// Intelligence demo, 29 October 2026: with located nodes drawn, opening the timeline (which shrinks
// the map's box) moved the camera to latitude -85, the edge of the projection, and the map went
// blank until another view was opened (ADR-086 Amendment 1).
import { expect, test } from "@playwright/test";

import { MAP_VIEW_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "MAP_VIEW_ACTIONS";

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


// The mitigation for CVE-2026-85061 (`06_DECISIONS.md`, ADR-014's accepted-risk amendment):
// MapLibre's own attribution control renders HTML through its broken `DOM.sanitize()`, so the map
// is built without it and the attribution is drawn by `MapView` as plain text. Before the GDS
// baseline audit (1 November 2026) nothing would have failed had the control been switched back
// on; shown red with `attributionControl: true` in `MapView.tsx`.
test("MapLibre's attribution control is never drawn; the attribution is plain text", async ({ page }) => {
  await page.goto("/keyboard/map-view-harness.html");
  await expect.poll(() => centre(page), { timeout: 20_000 }).not.toBeNull();
  await expect(page.locator(".maplibregl-ctrl-attrib")).toHaveCount(0);
  await expect(page.getByText("Harness tiles ©", { exact: true })).toBeVisible();
});

// P4 (`02_GLASS_FRONTEND.md` §3.5): the basemap switch and the place search, each by keyboard
// alone (rule 13): focus and key presses, never `page.mouse` or `.click()`.

async function sources(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const map = window.__MAP__;
    if (!map || !map.isStyleLoaded()) return null;
    return Object.keys(map.getStyle().sources);
  });
}

test("the basemap is switched by keyboard, the hosted one through the tile proxy", async ({ page }) => {
  await page.goto("/keyboard/map-view-harness.html");
  await expect.poll(() => sources(page), { timeout: 20_000 }).toContain("harness");
  const group = page.getByRole("group", { name: "Basemap" });
  await expect(group.getByRole("radio")).toHaveCount(2);
  await group.getByRole("radio", { name: "Harness", exact: true }).focus();
  await page.keyboard.press("ArrowDown");
  await expect(group.getByRole("radio", { name: "Hosted streets (hosted)" })).toBeChecked();
  // The map is drawn again from the chosen provider, its tiles from the Conduit's proxy route:
  // the Glass holds no address of the hosted provider's own, and no key.
  await expect
    .poll(async () => (await sources(page))?.filter((id) => !id.startsWith("ospreyflow-")), {
      timeout: 20_000,
    })
    .toEqual(["harness-hosted"]);
  const tiles = await page.evaluate(
    () => (window.__MAP__!.getStyle().sources["harness-hosted"] as { tiles: string[] }).tiles,
  );
  expect(tiles).toEqual(["/v1/map/tiles/harness-hosted/{z}/{x}/{y}"]);
  await expect(page.getByText("Hosted provider — per-deployment")).toBeVisible();
  await expect(page.getByText("Hosted streets ©", { exact: true })).toBeVisible();
  registerCovered(REGISTRY, "switch-the-basemap-by-keyboard");
});

test("a place is found in the case's gazetteer and shown by keyboard", async ({ page }) => {
  await page.goto("/keyboard/map-view-harness.html");
  await expect.poll(async () => (await centre(page))?.lat ?? 0, { timeout: 20_000 }).toBeGreaterThan(51.42);
  await page.getByRole("searchbox", { name: "Find a place" }).focus();
  await page.keyboard.type("cranf");
  await page.keyboard.press("Enter");
  const go = page.getByRole("button", { name: "Go to Cranford" });
  await expect(go).toBeVisible();
  await expect(page.getByRole("button", { name: "Go to Cranbrook" })).toHaveCount(0);
  expect(await page.evaluate(() => window.__PLACE_QUERIES__)).toEqual(["cranf"]);
  await page.keyboard.press("Tab"); // the Find button
  await page.keyboard.press("Tab");
  await expect(go).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator(".map-controls [role=status]")).toContainText("Showing Cranford.");
  // The camera goes to the place (Cranford, 51.488 N 0.459 W), well away from the yards.
  await expect
    .poll(async () => {
      const c = await centre(page);
      return c ? Math.abs(c.lat - 51.488) < 0.01 && Math.abs(c.lng + 0.459) < 0.01 : false;
    }, { timeout: 10_000 })
    .toBe(true);
  registerCovered(REGISTRY, "find-a-place-by-keyboard");
});

test("a name the gazetteer does not hold is said in words, and nothing else is asked", async ({ page }) => {
  await page.goto("/keyboard/map-view-harness.html");
  await page.getByRole("searchbox", { name: "Find a place" }).focus();
  await page.keyboard.type("Atlantis");
  await page.keyboard.press("Enter");
  await expect(page.locator(".map-controls [role=status]")).toContainText(
    "No place called “Atlantis” is in the gazetteer this case reads.",
  );
  expect(await page.evaluate(() => window.__PLACE_QUERIES__)).toEqual(["Atlantis"]);
});

test("every registered map view action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, MAP_VIEW_ACTIONS);
});
