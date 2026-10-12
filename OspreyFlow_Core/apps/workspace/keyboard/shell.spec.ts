// The workspace shell by keyboard alone (ADR-097 step 1, rule 13). No `page.mouse`, no `.click()`.
import { expect, test } from "@playwright/test";

import { SHELL_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "SHELL_ACTIONS";

declare global {
  interface Window {
    __TOPBAR__?: { opened: string | null; browsed: boolean; signedOut: boolean; rail: string[] };
  }
}

test("/ outside a text field moves focus to search", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await page.locator("body").focus();
  await page.keyboard.press("/");
  await expect(page.getByRole("combobox", { name: /Search entities/ })).toBeFocused();
  registerCovered(REGISTRY, "slash-moves-focus-to-search");
});

// DESIGN.md v0.3 §5a (ADR-115 decision 9): the strip 20, the workspace's top bar 44, the rail 48 with
// 36px buttons.
test("the marking strip and the top bar take 20 and 44 pixels, and the rail 48 with 36px buttons", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/top-bar-harness.html");
  const strip = (await page.getByRole("note", { name: "Protective marking" }).boundingBox())!;
  const bar = (await page.locator("header.top-bar").boundingBox())!;
  const railBox = (await page.getByRole("navigation", { name: "Workspace" }).boundingBox())!;
  expect(Math.round(strip.height)).toBe(20);
  expect(Math.round(bar.height)).toBe(44);
  expect(Math.round(railBox.width)).toBe(48);
  const item = (await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Cases" }).boundingBox())!;
  expect([Math.round(item.width), Math.round(item.height)]).toEqual([36, 36]);
  await expect(page.getByRole("note", { name: "Protective marking" })).toHaveText("OFFICIAL");
});

test("each rail entry is reached and pressed by keyboard", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  for (const name of ["Cases", "Watches", "Alerts", "Ownership", "History", "Explore", "Questions", "Ingest Studio", "Dashboards", "Admin"]) {
    await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name }).focus();
    await page.keyboard.press("Enter");
  }
  expect(await page.evaluate(() => window.__TOPBAR__?.rail)).toEqual(["cases", "watches", "alerts", "ownership", "history", "explore", "questions", "ingest", "dashboards", "admin"]);
  registerCovered(REGISTRY, "rail-entries-by-keyboard");
});

test("each view is chosen by keyboard, Reports among them", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  for (const name of ["Map", "Reports", "Graph"]) {
    await page.getByRole("button", { name, exact: true }).focus();
    await page.keyboard.press("Enter");
  }
  expect(await page.evaluate(() => window.__TOPBAR__?.views)).toEqual(["map", "reports", "graph"]);
  registerCovered(REGISTRY, "views-chosen-by-keyboard");
});

test("the rail shows its names, and hides them again, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  const rail = page.getByRole("navigation", { name: "Workspace" });
  await rail.getByRole("button", { name: "Show names" }).focus();
  await page.keyboard.press("Enter");
  await expect(rail.getByText("History")).toBeVisible();
  await expect(rail.getByRole("button", { name: "Hide names" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(rail.getByText("History")).toHaveCount(0);
  registerCovered(REGISTRY, "rail-shows-and-hides-names-by-keyboard");
});

// ADR-115 E6: Help at the rail's foot, by keyboard (it reopens the workspace's welcome panel).
test("the rail's Help is reached and pressed by keyboard", async ({ page }) => {
  await page.goto("/keyboard/top-bar-harness.html");
  await page.getByRole("navigation", { name: "Workspace" }).getByRole("button", { name: "Help" }).focus();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.__TOPBAR__?.help)).toBe(1);
  registerCovered(REGISTRY, "help-from-the-rail-by-keyboard");
});

test("every registered shell action has its own proving test case above", () => {
  assertAllCovered("SHELL_ACTIONS", SHELL_ACTIONS);
});
