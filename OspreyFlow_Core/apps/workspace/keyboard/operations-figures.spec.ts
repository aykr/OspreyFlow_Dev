// Admin › Running › Operations' figures by keyboard alone (ADR-141 decision 6; `CLAUDE.md` rule 13):
// a run quota is set and saved, and the figures are read again; a refused save is said in words. The
// harness records every request, so the case proves the action reached its route.
import { expect, test, type Page } from "@playwright/test";

import { OPERATIONS_FIGURES_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "OPERATIONS_FIGURES_ACTIONS";
const HARNESS = "/keyboard/operations-figures-harness.html";

function asked(page: Page): Promise<{ method: string; path: string; body?: string }[]> {
  return page.evaluate(() => (window as unknown as { __asked: { method: string; path: string; body?: string }[] }).__asked);
}

async function fill(page: Page, label: string, text: string) {
  await page.getByLabel(label, { exact: true }).focus();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type(text);
}

test("a unit's run quota is saved by keyboard, and the figures read again", async ({ page }) => {
  await page.goto(HARNESS);
  await expect(page.getByRole("table", { name: "Runs by day, pipeline and trigger" })).toBeVisible();
  await page.getByLabel("Quota for").focus();
  await page.getByLabel("Quota for").selectOption("unit");
  await fill(page, "Unit", "unit-1");
  await fill(page, "Runs a day", "5");
  await page.getByRole("button", { name: "Save the run quota" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("unit-1 may now start 5 runs a day.");
  const sent = await asked(page);
  const put = sent.find((a) => a.method === "PUT");
  expect(put?.path).toBe("/v1/admin/operations/quotas/unit/unit-1");
  expect(JSON.parse(put?.body ?? "{}")).toEqual({ runs_per_day: 5 });
  await expect.poll(async () => (await asked(page)).filter((a) => a.path === "/v1/admin/operations/runs").length).toBe(2);
  await expect(page.getByRole("table", { name: "Run quotas" })).toContainText("Unit unit-1");
  registerCovered(REGISTRY, "save-a-run-quota-by-keyboard");
});

test("a refused quota save is said in words, by keyboard", async ({ page }) => {
  await page.goto(`${HARNESS}?quota=refused`);
  await expect(page.getByRole("table", { name: "Run quotas" })).toBeVisible();
  await fill(page, "Dataset id", "harbour-extract");
  await fill(page, "Runs a day", "2");
  await page.getByRole("button", { name: "Save the run quota" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alert")).toHaveText(
    "Setting a quota needs Administer system: it binds every unit's runs into a dataset.",
  );
  registerCovered(REGISTRY, "read-a-refused-quota-save-by-keyboard");
});

test("every registered Operations figures action has its own proving test case above", () => {
  assertAllCovered("OPERATIONS_FIGURES_ACTIONS", OPERATIONS_FIGURES_ACTIONS);
});
