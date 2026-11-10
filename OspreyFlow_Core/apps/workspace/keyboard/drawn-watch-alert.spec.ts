// A drawn watch's alert by keyboard alone (ADR-143 Amendment 2 decision 8; L3.6; rule 13): open the
// alert a load raised on meeting a drawn item, from the one queue, and *Open the board* its drawn
// item is on. No `page.mouse`, no `.click()`. The effect is the board asked for, recorded by the
// harness (`window.__DRAWN_WATCH__`), not a control merely focused.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { DRAWN_WATCH_ALERT_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

async function press(page: Page, target: Locator): Promise<void> {
  await target.focus();
  await expect(target).toBeFocused();
  await page.keyboard.press("Enter");
}

test("Open the board, from a drawn watch's alert, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/drawn-watch-alert-harness.html");
  await press(page, page.getByRole("button", { name: /Open alert: Medium severity, A load met a drawn item — / }));
  const detail = page.getByRole("region", { name: "What fired this alert" });
  await expect(detail).toContainText("Jordan TALL looks like Tall");
  await press(page, detail.getByRole("button", { name: "Open the board" }));
  await expect.poll(() => page.evaluate(() => window.__DRAWN_WATCH__!.opened)).toEqual(["board-7"]);
  registerCovered("DRAWN_WATCH_ALERT_ACTIONS", "open-the-board-from-a-drawn-watch-alert-by-keyboard");
});

test("every registered drawn watch alert action has its own proving test case above", () => {
  assertAllCovered("DRAWN_WATCH_ALERT_ACTIONS", DRAWN_WATCH_ALERT_ACTIONS);
});
