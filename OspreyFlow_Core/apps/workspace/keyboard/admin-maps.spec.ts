// A keyboard-only walkthrough of Admin › Maps (ADR-147, `CLAUDE.md` rule 13): every action, by
// focus and key presses alone — no `page.mouse`, no `.click()` — each proving its call reached the
// Conduit's stand-in (`maps-harness.tsx`, which records each request).
import { expect, test, type Page } from "@playwright/test";

import { MAPS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "MAPS_ACTIONS";
const SYNTHETIC_KEY = "k-synthetic-keyboard-map-key";

const asked = (page: Page) => page.evaluate(() => (window as unknown as { mapsAsked: string[] }).mapsAsked);

async function press(page: Page, name: string) {
  await page.getByRole("button", { name, exact: true }).focus();
  await page.keyboard.press("Enter");
}

async function typeInto(page: Page, label: string | RegExp, text: string) {
  await page.getByLabel(label, { exact: typeof label === "string" }).focus();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type(text);
}

test.beforeEach(async ({ page }) => {
  await page.goto("/keyboard/maps-harness.html");
  await expect(page.getByRole("table", { name: "Map providers", exact: true })).toBeVisible();
});

test("a provider is added by keyboard", async ({ page }) => {
  await press(page, "Add a provider");
  await typeInto(page, "Provider id", "os-zoomstack");
  await typeInto(page, "Label analysts see", "OS Open Zoomstack");
  await typeInto(page, /Tile address/, "https://zoomstack.example.test/{z}/{x}/{y}.pbf");
  await typeInto(page, "Attribution shown on the map", "Contains OS data © Crown copyright");
  await typeInto(page, "Licence", "OGL-UK-3.0");
  await press(page, "Add the provider");
  await expect(page.getByRole("status")).toContainText("OS Open Zoomstack is added");
  expect(await asked(page)).toContain("POST /v1/admin/maps/providers");
  registerCovered(REGISTRY, "add-a-map-provider-by-keyboard");
});

test("a provider is edited by keyboard", async ({ page }) => {
  await press(page, "Edit Hosted tiles");
  await typeInto(page, "Label analysts see", "Hosted tiles (cached)");
  await press(page, "Save the provider");
  await expect(page.getByRole("status")).toContainText("Hosted tiles (cached) is saved");
  expect(await asked(page)).toContain("PUT /v1/admin/maps/providers/hosted");
  registerCovered(REGISTRY, "edit-a-map-provider-by-keyboard");
});

test("a provider's key is entered by keyboard, and the field is empty afterwards", async ({ page }) => {
  await press(page, "Enter key for Corporate aerial");
  await typeInto(page, /^Key for Corporate aerial/, SYNTHETIC_KEY);
  await page.keyboard.press("Enter");
  const sent = await page.evaluate(() => (window as unknown as { mapsKeysSent: unknown[] }).mapsKeysSent);
  expect(sent).toEqual([{ key: SYNTHETIC_KEY }]); // the typed key, and nothing else
  await expect(page.getByRole("status")).toContainText("the key is set");
  expect(await asked(page)).toContain("PUT /v1/admin/maps/providers/corporate/key");
  expect(await page.content()).not.toContain(SYNTHETIC_KEY);
  registerCovered(REGISTRY, "enter-a-map-key-by-keyboard");
});

test("a provider's key is removed by keyboard", async ({ page }) => {
  await press(page, "Remove key for Hosted tiles");
  await expect(page.getByRole("status")).toContainText("the key is removed");
  expect(await asked(page)).toContain("DELETE /v1/admin/maps/providers/hosted/key");
  registerCovered(REGISTRY, "remove-a-map-key-by-keyboard");
});

test("the map's default is chosen by keyboard", async ({ page }) => {
  await press(page, "Make the default: Hosted tiles");
  await expect(page.getByRole("status")).toContainText("The map now opens on Hosted tiles");
  expect(await asked(page)).toContain("PUT /v1/admin/maps/default");
  registerCovered(REGISTRY, "make-a-map-provider-the-default-by-keyboard");
});

test("a provider is removed by keyboard", async ({ page }) => {
  await press(page, "Remove Corporate aerial");
  await expect(page.getByRole("status")).toContainText("Corporate aerial is removed");
  expect(await asked(page)).toContain("DELETE /v1/admin/maps/providers/corporate");
  registerCovered(REGISTRY, "remove-a-map-provider-by-keyboard");
});

test("the basemap is built by keyboard, its lines shown", async ({ page }) => {
  await page.getByLabel("Region to build", { exact: true }).focus();
  await page.keyboard.type("rut"); // type-ahead on the closed list
  await press(page, "Build the basemap");
  await expect(page.getByRole("status")).toContainText("Built rutland.pmtiles.");
  await expect(page.getByRole("status")).toContainText("Running planetiler...");
  expect(await asked(page)).toContain("POST /v1/admin/geospatial/build-basemap");
  registerCovered(REGISTRY, "build-the-basemap-by-keyboard");
});

test("the providers are verified by keyboard", async ({ page }) => {
  await press(page, "Verify the providers");
  await expect(page.getByRole("status")).toContainText("Verify passed");
  expect(await asked(page)).toContain("POST /v1/admin/geospatial/verify");
  registerCovered(REGISTRY, "verify-the-map-providers-by-keyboard");
});

test("a prefetch area is added by keyboard", async ({ page }) => {
  await press(page, "Add a prefetch area");
  await typeInto(page, "Area name", "Second area");
  await typeInto(page, "West (degrees of longitude)", "-0.2");
  await typeInto(page, "South (degrees of latitude)", "51.4");
  await typeInto(page, "East (degrees of longitude)", "-0.1");
  await typeInto(page, "North (degrees of latitude)", "51.5");
  await press(page, "Add the area");
  await expect(page.getByRole("status")).toContainText("The area Second area is added");
  expect(await asked(page)).toContain("PUT /v1/admin/maps/areas");
  await expect(page.getByRole("table", { name: "Prefetch areas" })).toContainText("Second area");
  registerCovered(REGISTRY, "add-a-prefetch-area-by-keyboard");
});

test("a prefetch area is removed by keyboard", async ({ page }) => {
  await press(page, "Remove the area Area of operations");
  await expect(page.getByRole("status")).toContainText("The area Area of operations is removed");
  expect(await asked(page)).toContain("PUT /v1/admin/maps/areas");
  registerCovered(REGISTRY, "remove-a-prefetch-area-by-keyboard");
});

test("the prefetch schedule is set by keyboard", async ({ page }) => {
  await page.getByLabel("Fetch every area", { exact: true }).focus();
  await page.keyboard.type("Every w"); // "Every week"
  await expect(page.getByRole("status")).toContainText("The prefetch schedule is saved");
  expect(await asked(page)).toContain("PUT /v1/admin/maps/schedule");
  registerCovered(REGISTRY, "set-the-prefetch-schedule-by-keyboard");
});

test("every prefetch area is fetched now by keyboard", async ({ page }) => {
  await press(page, "Fetch every area now");
  await expect(page.getByRole("status")).toContainText("Every area is fetched.");
  await expect(page.getByRole("status")).toContainText("Area of operations: 21 fetched");
  expect(await asked(page)).toContain("POST /v1/admin/maps/prefetch");
  registerCovered(REGISTRY, "fetch-every-prefetch-area-now-by-keyboard");
});

test("every registered Maps action has its own proving test case above", () => {
  assertAllCovered("MAPS_ACTIONS", MAPS_ACTIONS);
});
