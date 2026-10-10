// A keyboard-only walkthrough of the pipeline canvas (ADR-108 phase A, rule 13): every node is a
// real button reached by Tab, and a node's settings are read without a pointer. No `page.mouse`,
// no `.click()`.
import { expect, test } from "@playwright/test";

import { PIPELINE_CANVAS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "PIPELINE_CANVAS_ACTIONS";

test("every pipeline node is reached by Tab, in flow order", async ({ page }) => {
  await page.goto("/keyboard/pipeline-canvas-harness.html");
  const names: string[] = [];
  for (let i = 0; i < 5; i++) {
    await page.keyboard.press("Tab");
    names.push(
      await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? ""),
    );
  }
  expect(names).toEqual([
    "Domain model: Domain model",
    "Source: Carrier B phone records",
    "Profile: Profile",
    "Map: Map",
    "Load: Load",
  ]);
  registerCovered(REGISTRY, "walk-the-pipeline-nodes-by-keyboard");
});

test("a node's settings are read by keyboard, and nothing in them is editable", async ({ page }) => {
  await page.goto("/keyboard/pipeline-canvas-harness.html");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab"); // the source node
  await page.keyboard.press("Enter");
  const details = page.getByRole("region", { name: "Node settings" });
  await expect(details).toBeVisible();
  await expect(details).toContainText("cell-site-csv");
  await expect(details).toContainText("uploaded/carrier-b.csv");
  expect(await details.getByRole("textbox").count()).toBe(0);
  registerCovered(REGISTRY, "read-a-nodes-settings-by-keyboard");
});

test("every registered pipeline-canvas action has its own proving test case above", () => {
  assertAllCovered("PIPELINE_CANVAS_ACTIONS", PIPELINE_CANVAS_ACTIONS);
});
