// The selection, by keyboard alone (ADR-093, rule 13): the canvas chip's Clear, and the Inspector
// list's Centre and Remove, each against the real canvas. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { SELECTION_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

declare global {
  interface Window {
    __KEYBOARD__?: { focused: string | null; selection: string[] };
  }
}

const selection = (page: Page) => page.evaluate(() => window.__KEYBOARD__?.selection ?? []);
const focused = (page: Page) => page.evaluate(() => window.__KEYBOARD__?.focused ?? null);

async function tabTo(page: Page, name: RegExp, max = 20) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const text = await page.evaluate(
      () => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? "",
    );
    if (name.test(text)) return;
  }
  throw new Error(`Tab never reached ${String(name)}`);
}

/** n0 is selected on focus; ArrowRight moves to a neighbour and Space adds it. */
async function selectTwo(page: Page) {
  await page.goto("/keyboard/harness.html");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await expect.poll(() => selection(page)).toEqual(["n0"]);
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => focused(page)).not.toBe("n0");
  const second = await focused(page);
  await page.keyboard.press(" ");
  await expect.poll(() => selection(page)).toEqual(["n0", second]);
  return second as string;
}

test("the chip says how many are selected, and its Clear empties the selection", async ({ page }) => {
  await selectTwo(page);
  await expect(page.getByRole("status").filter({ hasText: "2 selected" })).toBeVisible();
  await tabTo(page, /^Clear the selection$/);
  await page.keyboard.press("Enter");
  await expect.poll(() => selection(page)).toEqual([]);
  await expect(page.getByRole("status").filter({ hasText: "selected" })).toHaveCount(0);
  registerCovered("SELECTION_ACTIONS", "clear-the-selection-from-the-canvas-chip");
});

test("the list's name centres on that node and leaves the selection as it was", async ({ page }) => {
  await selectTwo(page);
  await expect(page.getByRole("heading", { name: "Selected (2)" })).toBeVisible();
  await tabTo(page, /^Centre on n0/);
  await page.keyboard.press("Enter");
  await expect.poll(() => focused(page)).toBe("n0");
  expect(await selection(page)).toHaveLength(2);
  registerCovered("SELECTION_ACTIONS", "centre-on-a-selected-node-from-the-list");
});

test("the list's × takes that node out of the selection", async ({ page }) => {
  const second = await selectTwo(page);
  await tabTo(page, new RegExp(`^Remove ${second} from the selection$`));
  await page.keyboard.press("Enter");
  await expect.poll(() => selection(page)).toEqual(["n0"]);
  registerCovered("SELECTION_ACTIONS", "remove-a-node-from-the-selection-from-the-list");
});

test("every registered selection action has its own proving test case above", () => {
  assertAllCovered("SELECTION_ACTIONS", SELECTION_ACTIONS);
});
