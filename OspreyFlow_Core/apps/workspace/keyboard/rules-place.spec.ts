// Rules and Monitoring by keyboard alone (ADR-146 decisions 2 and 6; `CLAUDE.md` rule 13): its four
// tabs, an alert opened from the queue at its own address, Back leaving it, an address opening its
// alert, and an address the reader may not see answered in the same words as one that does not exist.
// The switcher's way in is `shell.spec.ts`'s. No `page.mouse`, no `.click()`.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { RULES_PLACE_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "RULES_PLACE_ACTIONS";

async function press(page: Page, target: Locator): Promise<void> {
  await target.focus();
  await expect(target).toBeFocused();
  await page.keyboard.press("Enter");
}

for (const brand of ["ospreyflow", "govuk"] as const) {
  test(`${brand}: each of the place's tabs is reached and opened by keyboard`, async ({ page }) => {
    await page.goto(`/keyboard/rules-place-harness.html?brand=${brand}`);
    await expect(page.getByRole("heading", { name: "Rules and Monitoring" })).toBeVisible();
    await expect(page.getByRole("tab")).toHaveText(["Alerts", "What raises alerts", "Held rows", "Changes"]);
    for (const name of ["What raises alerts", "Held rows", "Changes", "Alerts"]) {
      await press(page, page.getByRole("tab", { name, exact: true }));
      await expect(page.getByRole("tab", { name, exact: true })).toHaveAttribute("aria-selected", "true");
    }
    await expect(page.getByRole("region", { name: "Alert queue" })).toBeVisible();
    registerCovered(REGISTRY, "move-between-the-tabs-by-keyboard");
  });
}

test("an alert opened from the queue is given its address, and Back leaves it, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/rules-place-harness.html");
  const row = page.getByRole("button", { name: /Open alert:.*Structuring/ });
  await press(page, row);
  await expect(page).toHaveURL(/\/alerts\/a1(\?|$)/);
  await expect(row).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Claim" })).toBeVisible();
  // The browser's own Back (the browser's action, not the page's): the alert is left, the queue stays.
  await page.goBack();
  await expect(page).toHaveURL(/rules-place-harness\.html/);
  await expect(row).toHaveAttribute("aria-pressed", "false");
  registerCovered(REGISTRY, "open-an-alert-at-its-address-by-keyboard");
});

test("an address opens its alert, beside the queue", async ({ page }) => {
  await page.goto("/keyboard/rules-place-harness.html?address=a1");
  await expect(page.getByRole("button", { name: /Open alert:.*Structuring/ })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Claim" })).toBeVisible();
});

test("another case's alert is opened by moving to that case, on the alert", async ({ page }) => {
  await page.goto("/keyboard/rules-place-harness.html?address=a-other");
  await expect.poll(() => page.evaluate(() => window.__RULES__?.went)).toEqual(["/alerts/a-other?investigation=inv-2&from=case"]);
  await expect(page.getByText("Opening the alert…")).toBeVisible();
});

test("an address the reader may not see says so as for a missing alert, and Back to the queue leaves it, by keyboard", async ({
  page,
}) => {
  await page.goto("/keyboard/rules-place-harness.html?address=not-yours");
  await expect(page.getByRole("alert")).toHaveText("There is no alert at this address that you can see.");
  await press(page, page.getByRole("button", { name: "← Back to the queue" }));
  await expect(page).toHaveURL(/rules-place-harness\.html/);
  await expect(page.getByRole("region", { name: "Alert queue" })).toBeVisible();
  registerCovered(REGISTRY, "back-to-the-queue-from-an-address-by-keyboard");
});

test("every registered Rules and Monitoring action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, RULES_PLACE_ACTIONS);
});
