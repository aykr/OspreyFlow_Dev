// The side panel's and the timeline's hide and full-width buttons, reached with the keyboard alone
// (rule 13): each button is focused and pressed with Enter. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { PANEL_FRAME_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "PANEL_FRAME_ACTIONS";
const URL = "/keyboard/panel-frames-harness.html";
test.use({ viewport: { width: 1200, height: 800 } });

const widthOf = async (page: Page, selector: string) => (await page.locator(selector).boundingBox())!.width;
const panel = (page: Page) => page.getByRole("region", { name: "Inspector" });

async function press(page: Page, name: string | RegExp) {
  const button = page.getByRole("button", { name });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

test("Hide leaves a strip with the contents kept, and Show brings the panel back", async ({ page }) => {
  await page.goto(URL);
  expect(await widthOf(page, "[data-panel-mode]")).toBeCloseTo(320, -1); // 320 and a 1px border
  await page.getByLabel("Query", { exact: true }).fill("person where family_name = Volkov");
  await press(page, "Hide the inspector");
  await expect(panel(page)).toHaveAttribute("data-panel-mode", "collapsed");
  expect(await widthOf(page, "[data-panel-mode]")).toBeLessThan(60);
  await press(page, "Show the inspector");
  await expect(panel(page)).toHaveAttribute("data-panel-mode", "normal");
  await expect(page.getByLabel("Query", { exact: true })).toHaveValue("person where family_name = Volkov");
  registerCovered(REGISTRY, "hide-and-show-the-side-panel-by-keyboard");
});

test("Full width covers the whole work area, and Normal width returns it", async ({ page }) => {
  await page.goto(URL);
  await press(page, "Open the inspector to the full width");
  await expect(panel(page)).toHaveAttribute("data-panel-mode", "full");
  const work = (await page.locator("#work-area").boundingBox())!;
  const full = (await page.locator("[data-panel-mode]").boundingBox())!;
  expect(Math.round(full.width)).toBe(Math.round(work.width));
  expect(Math.round(full.height)).toBe(Math.round(work.height));
  await press(page, "Return the inspector to its normal width");
  await expect(panel(page)).toHaveAttribute("data-panel-mode", "normal");
  expect(await widthOf(page, "[data-panel-mode]")).toBeCloseTo(320, -1); // 320 and a 1px border
  registerCovered(REGISTRY, "open-the-side-panel-to-the-full-width-and-return-by-keyboard");
});

test("Hide the timeline gives its height back, and Show restores it", async ({ page }) => {
  await page.goto(URL);
  const before = (await page.locator("#work-area").boundingBox())!.height;
  await press(page, "Hide the timeline");
  await expect.poll(async () => (await page.locator("#work-area").boundingBox())!.height).toBeGreaterThan(before + 200);
  await expect(page.getByRole("button", { name: "Show the timeline" })).toHaveAttribute("aria-expanded", "false");
  await press(page, "Show the timeline");
  await expect.poll(async () => Math.round((await page.locator("#work-area").boundingBox())!.height)).toBe(Math.round(before));
  registerCovered(REGISTRY, "hide-and-show-the-timeline-by-keyboard");
});

const slotOrder = (page: Page) =>
  page.locator("[data-panel-slot]").evaluateAll((els) => els.map((el) => el.getAttribute("data-panel-slot")));

test("Move up and Move down reorder the panels with Enter alone, and the order survives a reload", async ({ page }) => {
  await page.goto(URL);
  expect(await slotOrder(page)).toEqual(["inspector", "metrics", "query-builder"]);
  await press(page, "Move the metrics up");
  expect(await slotOrder(page)).toEqual(["metrics", "inspector", "query-builder"]);
  // Now at the top: the same button is unavailable, does nothing, and still has focus (ADR-085).
  const up = page.getByRole("button", { name: "Move the metrics up" });
  await expect(up).toHaveAttribute("aria-disabled", "true");
  await expect(up).toBeFocused();
  await page.keyboard.press("Enter");
  expect(await slotOrder(page)).toEqual(["metrics", "inspector", "query-builder"]);
  await expect(up).toBeFocused();
  await press(page, "Move the query builder up");
  expect(await slotOrder(page)).toEqual(["metrics", "query-builder", "inspector"]);
  await page.reload();
  expect(await slotOrder(page)).toEqual(["metrics", "query-builder", "inspector"]);
  registerCovered(REGISTRY, "move-a-side-panel-up-and-down-by-keyboard");
});

test("every registered panel-frame action has its own proving test case above", () => {
  assertAllCovered("PANEL_FRAME_ACTIONS", PANEL_FRAME_ACTIONS);
});
