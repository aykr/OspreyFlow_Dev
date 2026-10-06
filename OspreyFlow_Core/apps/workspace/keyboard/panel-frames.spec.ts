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
  // The moves sit in each header's menu (ADR-097 step 1): opened with Enter first.
  await press(page, "Arrange the metrics");
  await expect(page.getByRole("button", { name: "Arrange the metrics" })).toHaveAttribute("aria-expanded", "true");
  await press(page, "Move the metrics up");
  expect(await slotOrder(page)).toEqual(["metrics", "inspector", "query-builder"]);
  // Now at the top: the same button is unavailable, does nothing, and still has focus (ADR-085).
  const up = page.getByRole("button", { name: "Move the metrics up" });
  await expect(up).toHaveAttribute("aria-disabled", "true");
  await expect(up).toBeFocused();
  await page.keyboard.press("Enter");
  expect(await slotOrder(page)).toEqual(["metrics", "inspector", "query-builder"]);
  await expect(up).toBeFocused();
  await press(page, "Arrange the query builder");
  await press(page, "Move the query builder up");
  expect(await slotOrder(page)).toEqual(["metrics", "query-builder", "inspector"]);
  await page.reload();
  expect(await slotOrder(page)).toEqual(["metrics", "query-builder", "inspector"]);
  registerCovered(REGISTRY, "move-a-side-panel-up-and-down-by-keyboard");
});

test("Alt+Up and Alt+Down on a panel's header move it, with no menu opened", async ({ page }) => {
  await page.goto(URL);
  const header = page.getByRole("button", { name: "Arrange the query builder" });
  await header.focus();
  await page.keyboard.press("Alt+ArrowUp");
  expect(await slotOrder(page)).toEqual(["inspector", "query-builder", "metrics"]);
  await expect(header).toBeFocused();
  await page.keyboard.press("Alt+ArrowUp");
  expect(await slotOrder(page)).toEqual(["query-builder", "inspector", "metrics"]);
  // At the top Alt+Up does nothing; Alt+Down takes it back.
  await page.keyboard.press("Alt+ArrowUp");
  expect(await slotOrder(page)).toEqual(["query-builder", "inspector", "metrics"]);
  await page.keyboard.press("Alt+ArrowDown");
  expect(await slotOrder(page)).toEqual(["inspector", "query-builder", "metrics"]);
  await expect(header).toHaveAttribute("aria-expanded", "false");
  registerCovered(REGISTRY, "move-a-side-panel-with-alt-arrows-by-keyboard");
});

async function focusSash(page: Page, name: string) {
  const sash = page.getByRole("separator", { name });
  await sash.focus();
  await expect(sash).toBeFocused();
  return sash;
}

test("the side panel's sash widens and narrows the column with the arrow keys, Home resets it, and the width survives a reload", async ({
  page,
}) => {
  await page.goto(URL);
  expect(await widthOf(page, "[data-panel-mode]")).toBeCloseTo(320, -1);
  const sash = await focusSash(page, "Resize the side panel");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(() => widthOf(page, "[data-panel-mode]")).toBeCloseTo(352, -1);
  await expect(sash).toHaveAttribute("aria-valuenow", "352");
  // The canvas gave the room up: the two share the work area.
  const work = (await page.locator("#work-area").boundingBox())!;
  const canvas = (await page.locator("#canvas-stand-in").boundingBox())!;
  expect(Math.round(canvas.width + 352)).toBe(Math.round(work.width));
  await page.keyboard.press("Shift+ArrowRight"); // a large step back
  await expect(sash).toHaveAttribute("aria-valuenow", "288");
  await page.reload();
  await expect.poll(() => widthOf(page, "[data-panel-mode]")).toBeCloseTo(288, -1);
  await focusSash(page, "Resize the side panel");
  await page.keyboard.press("Home");
  await expect.poll(() => widthOf(page, "[data-panel-mode]")).toBeCloseTo(320, -1);
  registerCovered(REGISTRY, "resize-the-side-panel-by-keyboard");
});

test("a stacked panel's sash gives it a height of its own, and Home lets it share again", async ({ page }) => {
  await page.goto(URL);
  const slot = page.locator('[data-panel-slot="inspector"]');
  const before = (await slot.boundingBox())!.height;
  await focusSash(page, "Resize the inspector");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await expect.poll(async () => Math.round((await slot.boundingBox())!.height)).toBe(Math.round(before) + 32);
  await page.keyboard.press("Home");
  await expect.poll(async () => Math.round((await slot.boundingBox())!.height)).toBe(Math.round(before));
  registerCovered(REGISTRY, "resize-a-stacked-panel-by-keyboard");
});

test("the timeline's sash raises and lowers it with the arrow keys, and the height survives a reload", async ({ page }) => {
  await page.goto(URL);
  const body = page.locator("#timeline-body");
  expect(Math.round((await body.boundingBox())!.height)).toBe(252);
  await focusSash(page, "Resize the timeline");
  await page.keyboard.press("ArrowUp");
  await expect.poll(async () => Math.round((await body.boundingBox())!.height)).toBe(268);
  await page.reload();
  await expect.poll(async () => Math.round((await body.boundingBox())!.height)).toBe(268);
  await focusSash(page, "Resize the timeline");
  await page.keyboard.press("Home");
  await expect.poll(async () => Math.round((await body.boundingBox())!.height)).toBe(252);
  registerCovered(REGISTRY, "resize-the-timeline-by-keyboard");
});

test("every registered panel-frame action has its own proving test case above", () => {
  assertAllCovered("PANEL_FRAME_ACTIONS", PANEL_FRAME_ACTIONS);
});
