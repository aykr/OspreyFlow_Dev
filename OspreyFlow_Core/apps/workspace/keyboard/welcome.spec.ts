// A keyboard-only walkthrough of the workspace's welcome panel (ADR-115 E6, `CLAUDE.md` rule 13): `?`
// opens it (never while typing), a history step restores by Enter, and its own button closes it.
import { expect, test } from "@playwright/test";

import { WELCOME_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

test("? opens the panel, never while typing; a step restores by keyboard; Close shuts it", async ({ page }) => {
  await page.route("**/*/v1/investigations/c1/history", (route) =>
    route.fulfill({ status: 200, contentType: "application/json",
                    body: JSON.stringify([{ id: "s1", label: "Expanded", created_at: new Date().toISOString() }]) }),  // prettier-ignore
  );
  await page.route("**/*/v1/investigations/c1/history/s1", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ seq: 41, nodes: [], edges: [] }) }),
  );
  await page.goto("/keyboard/welcome-harness.html");
  await page.getByRole("textbox", { name: "A text field" }).focus();
  await page.keyboard.type("?");
  await expect(page.getByRole("dialog", { name: "Welcome back" })).toHaveCount(0);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: "Welcome back" })).toBeVisible();
  registerCovered("WELCOME_ACTIONS", "open-the-welcome-panel-with-question-mark");

  const step = page.getByRole("button", { name: /Expanded/ });
  await step.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__WELCOME__?.restored)).toEqual([41]);
  await expect(page.getByRole("dialog", { name: "Welcome back" })).toHaveCount(0);
  registerCovered("WELCOME_ACTIONS", "pick-up-a-history-step-from-the-welcome-panel");

  await page.keyboard.press("?");
  await page.getByRole("button", { name: "Close the welcome panel" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Welcome back" })).toHaveCount(0);
  registerCovered("WELCOME_ACTIONS", "close-the-welcome-panel");
});

test("every registered welcome-panel action has its own proving test case above", () => {
  assertAllCovered("WELCOME_ACTIONS", WELCOME_ACTIONS);
});
