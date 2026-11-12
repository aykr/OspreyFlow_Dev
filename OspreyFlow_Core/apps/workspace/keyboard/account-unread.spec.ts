// The account-unread notice by keyboard alone (ADR-148 Amendment 8; `CLAUDE.md` rule 13): when the
// Conduit cannot say who the person is, *Try again* and *Sign out* are each reached by Tab and pressed
// with the keyboard. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import {
  ACCOUNT_UNREAD_ACTIONS,
  assertAllCovered,
  registerCovered,
} from "./actionRegistry";

const REGISTRY = "ACCOUNT_UNREAD_ACTIONS";
const HARNESS = "/keyboard/account-unread-harness.html";

function acted(page: Page): Promise<string[]> {
  return page.evaluate(
    () => (window as unknown as { __acted: string[] }).__acted,
  );
}

test("the account is asked for again by keyboard when it could not be read", async ({
  page,
}) => {
  await page.goto(HARNESS);
  await expect(page.getByRole("alert")).toContainText(
    "Your account could not be read just now",
  );
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Try again" })).toBeFocused();
  await page.keyboard.press("Enter");
  expect(await acted(page)).toEqual(["try-again"]);
  registerCovered(REGISTRY, "try-reading-the-account-again-by-keyboard");
});

test("Sign out is reached by keyboard with no account read", async ({
  page,
}) => {
  await page.goto(HARNESS);
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeFocused();
  await page.keyboard.press("Space");
  expect(await acted(page)).toEqual(["sign-out"]);
  registerCovered(REGISTRY, "sign-out-with-no-account-read-by-keyboard");
});

test("every registered account-unread action has its own proving test case above", () => {
  assertAllCovered("ACCOUNT_UNREAD_ACTIONS", ACCOUNT_UNREAD_ACTIONS);
});
