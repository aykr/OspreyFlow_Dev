// A keyboard-only walkthrough of the Trends tab (ADR-113 stage 5, `CLAUDE.md` rule 13): build and
// preview a trend, save it, and add a saved trend to a pack — no `page.mouse`, no `.click()`; each
// proves its call reached the server with the right body.
import { expect, test, type Page } from "@playwright/test";

import { TRENDS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";
import { PACK, SAVED_TREND, serveWorld, world } from "./reportsFixtures";

const REGISTRY = "TRENDS_ACTIONS";

/** Reaches a tab the way a keyboard user does: from the first tab, with Tab, then Enter. */
async function openTab(page: Page, stepsFromFigures: number) {
  await page.getByRole("tab", { name: "Figures" }).focus();
  for (let i = 0; i < stepsFromFigures; i++) await page.keyboard.press("Tab");
  await page.keyboard.press("Enter");
}

async function fillBuilder(page: Page) {
  await page.getByLabel("Title").focus();
  await page.keyboard.type("Payments by channel");
  await page.getByLabel("Payments", { exact: true }).focus();
  await page.keyboard.press("Space");
  await page.getByLabel("Sum", { exact: true }).focus();
  await page.keyboard.press("Space");
  await page.getByRole("combobox", { name: "Property to add up" }).selectOption("amount");
  await page.getByRole("combobox", { name: "Weeks back" }).selectOption("26");
  await page.getByRole("combobox", { name: "Series" }).selectOption("channel");
}

const DEFINITION = {
  title: "Payments by channel", event_types: ["payment"], measure: "sum", measure_field: "amount",
  interval: "week", weeks: 26, group_by: "channel", filters: [],
};  // prettier-ignore

test("a trend is built and previewed by keyboard", async ({ page }) => {
  const calls = await serveWorld(page, world());
  await page.goto("/keyboard/trends-harness.html");
  await openTab(page, 1);
  await expect(page.getByLabel("Payments", { exact: true })).toBeVisible();
  await fillBuilder(page);
  await page.getByRole("button", { name: "Preview" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("img", { name: /Payments by channel/ })).toBeVisible();
  expect(calls.find((c) => c.path === "trends/preview")?.body).toEqual(DEFINITION);
  await expect(page.getByText("Marked OFFICIAL")).toBeVisible();
  registerCovered(REGISTRY, "build-and-preview-a-trend-by-keyboard");
});

test("a trend is saved by keyboard", async ({ page }) => {
  const calls = await serveWorld(page, world());
  await page.goto("/keyboard/trends-harness.html");
  await openTab(page, 1);
  await expect(page.getByLabel("Payments", { exact: true })).toBeVisible();
  await fillBuilder(page);
  await page.getByRole("button", { name: "Save trend" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Payments by channel" })).toBeVisible();
  expect(calls.find((c) => c.method === "POST" && c.path === "trends")?.body).toEqual(DEFINITION);
  registerCovered(REGISTRY, "save-a-trend-by-keyboard");
});

test("a saved trend is added to a pack by keyboard", async ({ page }) => {
  const calls = await serveWorld(page, world({ trends: [SAVED_TREND], packs: [PACK] }));
  await page.goto("/keyboard/trends-harness.html");
  await openTab(page, 1);
  await page.getByRole("button", { name: "Payments by channel" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("img", { name: /Payments by channel/ })).toBeVisible();
  await page.getByRole("combobox", { name: "Pack" }).selectOption("p1");
  await page.getByRole("button", { name: "Add to pack" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Added to Quarter pack")).toBeVisible();
  expect(calls.find((c) => c.method === "POST" && c.path === "packs/p1/items")?.body).toEqual({ kind: "trend", trend_id: "t1" });
  registerCovered(REGISTRY, "add-a-trend-to-a-pack-by-keyboard");
});

test("every registered Trends action has its own proving test case above", () => {
  assertAllCovered("TRENDS_ACTIONS", TRENDS_ACTIONS);
});
