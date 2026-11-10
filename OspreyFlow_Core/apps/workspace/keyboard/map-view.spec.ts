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
  await expect(page.locator(".map-controls__search [role=status]")).toContainText("Showing Cranford.");
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
  await expect(page.locator(".map-controls__search [role=status]")).toContainText(
    "No place called “Atlantis” is in the gazetteer this case reads.",
  );
  expect(await page.evaluate(() => window.__PLACE_QUERIES__)).toEqual(["Atlantis"]);
});

// P6 (ADR-147 Amendment 2, the owner's ruling 6): the case's gazetteers beside the place search,
// added and removed by keyboard alone. The panel follows the search in the tab order. A change is
// held open by the harness until the case releases it, as a real copy takes seconds, so the
// pressed button is seen to keep the focus while it runs.

const PANEL = "Gazetteers in this case's dataset";

test("a gazetteer is added by keyboard, the search asked again, then removed again", async ({ page }) => {
  await page.goto("/keyboard/map-view-harness.html");
  await page.getByRole("searchbox", { name: "Find a place" }).focus();
  await page.keyboard.type("cran");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Go to Cranford" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Go to Cranwell" })).toHaveCount(0);
  // Tab past Find, Go to Cranford and Go to Cranbrook, to the first gazetteer's button.
  for (let stop = 0; stop < 4; stop += 1) await page.keyboard.press("Tab");
  const panel = page.getByRole("region", { name: PANEL });
  const add = panel.getByRole("button", { name: "Add Harness towns" });
  await expect(add).toBeFocused();
  await page.evaluate(() => (window.__HOLD_GAZETTEER__ = true));
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status")).toContainText("Adding Harness towns…");
  await expect(add).toBeFocused();
  await expect(add).toHaveAttribute("aria-disabled", "true");
  await page.keyboard.press("Enter"); // a second press while it runs does nothing
  await page.evaluate(() => window.__RELEASE_GAZETTEER__!());
  await expect(panel.getByRole("status")).toContainText(
    "Harness towns is added: its places are copied into this case's dataset",
  );
  const remove = panel.getByRole("button", { name: "Remove Harness towns" });
  await expect(remove).toBeFocused();
  await expect(panel.getByRole("listitem").first()).toContainText("— added");
  // The search shown is asked again, and now offers the added gazetteer's place.
  await expect(page.getByRole("button", { name: "Go to Cranwell" })).toBeVisible();
  expect(await page.evaluate(() => window.__PLACE_QUERIES__)).toEqual(["cran", "cran"]);
  registerCovered(REGISTRY, "add-a-gazetteer-by-keyboard");

  // Removed again at once: the Conduit's words, and the place no longer offered.
  await page.evaluate(() => (window.__HOLD_GAZETTEER__ = false));
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status")).toContainText(
    "The gazetteer is removed: its places stay in this dataset as its own",
  );
  await expect(add).toBeFocused();
  await expect(page.getByRole("button", { name: "Go to Cranwell" })).toHaveCount(0);
  expect(await page.evaluate(() => window.__GAZETTEER_CALLS__)).toEqual([
    "PUT ds-harness gazetteer-harness-towns",
    "DELETE ds-harness gazetteer-harness-towns",
  ]);
});

test("a gazetteer already added is removed by keyboard", async ({ page }) => {
  await page.goto("/keyboard/map-view-harness.html?gazetteers=added");
  const panel = page.getByRole("region", { name: PANEL });
  await expect(panel).toBeVisible();
  await page.getByRole("searchbox", { name: "Find a place" }).focus();
  await page.keyboard.press("Tab"); // the Find button
  await page.keyboard.press("Tab"); // the first gazetteer's button
  await expect(panel.getByRole("button", { name: "Remove Harness towns" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status")).toContainText(
    "The gazetteer is removed: its places stay in this dataset as its own",
  );
  expect(await page.evaluate(() => window.__GAZETTEER_CALLS__)).toEqual([
    "DELETE ds-harness gazetteer-harness-towns",
  ]);
  await expect(panel.getByRole("button", { name: "Add Harness towns" })).toBeFocused();
  registerCovered(REGISTRY, "remove-a-gazetteer-by-keyboard");
});

test("without run_pipelines no change is offered, and Tab passes the panel by", async ({ page }) => {
  await page.goto("/keyboard/map-view-harness.html?gazetteers=reader");
  const panel = page.getByRole("region", { name: PANEL });
  await expect(panel).toContainText("Adding or removing a gazetteer needs the right to run pipelines.");
  await expect(panel.getByRole("button")).toHaveCount(0);
  await page.getByRole("searchbox", { name: "Find a place" }).focus();
  await page.keyboard.press("Tab"); // the Find button
  await page.keyboard.press("Tab"); // past the panel: where an Add would be, there is none
  expect(
    await page.evaluate(() => document.activeElement?.closest(".map-controls__gazetteers") ?? null),
  ).toBeNull();
  expect(await page.evaluate(() => window.__GAZETTEER_CALLS__)).toEqual([]);
});

test("every registered map view action has its own proving test case above", () => {
  assertAllCovered("MAP_VIEW_ACTIONS", MAP_VIEW_ACTIONS);
});
