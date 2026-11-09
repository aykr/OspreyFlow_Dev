// A keyboard-only walkthrough of L2.12 (`CLAUDE.md` rule 13; ADR-145 Amendment 4 decisions 8–10 and
// 12, ADR-146 decision 9): the Figures' Alerts panel, the Alert monitoring board first on the
// Dashboards, the Reports Viewer's two ways on from an alert and its way back, and the help page's way
// back. No `page.mouse`, no `.click()`: focus and keys only, each proving the action reached its
// handler (`window.__DID__`, written by the harness).
import { expect, test, type Page } from "@playwright/test";

import { ALERT_FIGURES_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "ALERT_FIGURES_ACTIONS";
const did = (page: Page) => page.evaluate(() => window.__DID__ ?? []);

test("the newest alert on the Figures' Alerts panel opens at its address by keyboard", async ({ page }) => {
  await page.goto("/keyboard/alert-figures-harness.html");
  const newest = page.getByRole("list", { name: "Newest alerts" }).getByRole("button", { name: /Synthetic Person A/ });
  await newest.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => did(page)).toContain("open alert a14");
  registerCovered(REGISTRY, "open-the-newest-alert-from-the-alerts-panel-by-keyboard");
});

test("Back to your alerts, from the Figures opened from an alert, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/alert-figures-harness.html?from=alert");
  const back = page.getByRole("button", { name: "← Back to your alerts" });
  await expect(back).toBeFocused();
  await expect.poll(() => did(page)).toContain("GET /v1/investigations/inv-1/reports?weeks=4");
  await page.keyboard.press("Enter");
  await expect.poll(() => did(page)).toContain("back to your alerts");
  registerCovered(REGISTRY, "go-back-to-your-alerts-from-the-figures-by-keyboard");
});

test("the Alert monitoring board and a Superset board are chosen by keyboard", async ({ page }) => {
  await page.goto("/keyboard/alert-figures-harness.html?board=1");
  await expect(page.getByRole("region", { name: "Alert monitoring" })).toBeVisible();
  await page.getByRole("button", { name: "Fraud board" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => did(page)).toContain("embed uuid-fraud");
  await expect(page.getByRole("region", { name: "Alert monitoring" })).toHaveCount(0);
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button", { name: "Alert monitoring" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Alert monitoring" })).toBeVisible();
  expect((await did(page)).filter((d) => d.includes("guest-token"))).toHaveLength(1);
  registerCovered(REGISTRY, "choose-the-alert-monitoring-board-and-a-superset-board-by-keyboard");
});

test("the Alert monitoring board is filtered to a rule by keyboard", async ({ page }) => {
  await page.goto("/keyboard/alert-figures-harness.html?board=1");
  const raised = page.getByRole("list", { name: "Raised by rule" });
  await expect(raised.getByRole("listitem")).toHaveCount(2);
  // A native select, operated by the platform's own keys — the convention `reports.spec.ts` follows.
  await page.getByRole("combobox", { name: "Rule" }).selectOption("hotlists:");
  await expect(raised.getByRole("listitem")).toHaveText(["Hotlists: 2"]);
  registerCovered(REGISTRY, "filter-the-alert-monitoring-board-by-keyboard");
});

test("Back to your alerts, from the board opened from an alert, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/alert-figures-harness.html?board=1&rule=hotlists&from=alert");
  await expect(page.getByRole("combobox", { name: "Rule" })).toHaveValue("hotlists:");
  await expect(page.getByRole("button", { name: "← Back to your alerts" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => did(page)).toContain("back to your alerts");
  registerCovered(REGISTRY, "go-back-to-your-alerts-from-the-board-by-keyboard");
});

test("a Reports Viewer opens an alert's case on its Figures, and its dashboard, from Home by keyboard", async ({ page }) => {
  await page.goto("/keyboard/alert-figures-harness.html?home=1");
  const row = page.getByRole("group", { name: /Hotlist alert in Operation Kestrel/ });
  await row.getByRole("button", { name: "Open in its case" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => did(page)).toContain("journey figures inv-1 a14 hotlists");
  registerCovered(REGISTRY, "open-an-alerts-case-figures-from-home-by-keyboard");
  await page.keyboard.press("Tab");
  await expect(row.getByRole("button", { name: "Open the dashboard" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => did(page)).toContain("journey board inv-1 a14 hotlists");
  expect((await did(page)).some((d) => d.startsWith("open alert"))).toBe(false);
  registerCovered(REGISTRY, "open-an-alerts-dashboard-from-home-by-keyboard");
});

test("the Roles, teams and Authors page is left by keyboard", async ({ page }) => {
  await page.goto("/keyboard/alert-figures-harness.html?help=1");
  await expect(page.getByRole("button", { name: "← Back to Admin" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => did(page)).toContain("back to Admin");
  registerCovered(REGISTRY, "go-back-from-the-roles-help-page-by-keyboard");
});

test("every registered L2.12 action has its own proving test case above", () => {
  assertAllCovered("ALERT_FIGURES_ACTIONS", ALERT_FIGURES_ACTIONS);
});
