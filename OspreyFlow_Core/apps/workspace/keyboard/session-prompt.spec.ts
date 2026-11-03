// A keyboard-only walkthrough of the prompt shown in place when the token could not be renewed
// (ADR-050 Amendment 1, build order step 18b, `CLAUDE.md` rule 13): focus starts inside it, Enter on
// "Sign in again" asks for the sign-in window, and the page behind it is kept; in the unreachable form
// "Try again" comes first, and Tab stays inside the prompt. This test never calls `.click()`.
import { expect, test } from "@playwright/test";

import { SESSION_PROMPT_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

test("an ended session: Enter on Sign in again asks for the sign-in window, and the page is kept", async ({ page }) => {
  await page.goto("/keyboard/session-prompt-harness.html");
  const prompt = page.getByRole("alertdialog", { name: "Your session has ended" });
  await expect(prompt).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in again" })).toBeFocused();

  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__SESSION__!.signInAgain)).toBe(1);
  await expect(prompt).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "A sentence being written" })).toHaveValue(
    "Money straight through an account",
  );
  registerCovered("SESSION_PROMPT_ACTIONS", "sign-in-again-from-the-session-prompt-by-keyboard");
});

test("an unreachable sign-in service: Enter on Try again tries again; Tab stays inside the prompt", async ({ page }) => {
  await page.goto("/keyboard/session-prompt-harness.html?why=unreachable");
  await expect(page.getByRole("alertdialog", { name: "The sign-in service could not be reached" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeFocused();

  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__SESSION__!.tryAgain)).toBe(1);

  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Sign in again" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Try again" })).toBeFocused();
  registerCovered("SESSION_PROMPT_ACTIONS", "try-again-from-the-session-prompt-by-keyboard");
});

test("every registered session prompt action has its own proving test case above", () => {
  assertAllCovered("SESSION_PROMPT_ACTIONS", SESSION_PROMPT_ACTIONS);
});
