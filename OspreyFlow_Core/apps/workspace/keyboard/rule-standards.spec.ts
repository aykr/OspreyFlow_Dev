// A keyboard-only walkthrough of *Show as BPMN* (`06_DECISIONS.md` ADR-146 decision 3; `CLAUDE.md`
// rule 13): the drawing opens by Enter, is read, keeps focus inside, and closes by Escape and by
// *Close*, each giving focus back to the button it opened from (rule 12: proved, not only opened).
// No `page.mouse`, no `.click()`. The drawing is of the `.bpmn` the codec really writes. Synthetic
// data only (rule 9).
import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  RULE_STANDARDS_ACTIONS,
  assertAllCovered,
  registerCovered,
} from "./actionRegistry";

const REGISTRY = "RULE_STANDARDS_ACTIONS";

async function press(page: Page, target: Locator, key = "Enter") {
  await target.focus();
  await page.keyboard.press(key);
}

test("Show as BPMN opens the rule's drawing by keyboard, and it is read", async ({
  page,
}) => {
  await page.goto("/keyboard/rule-standards-harness.html");
  const button = page.getByRole("button", { name: "Show as BPMN" });
  await press(page, button);
  const dialog = page.getByRole("dialog", {
    name: "Visits to listed people as BPMN 2.0",
  });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("img")).toHaveAttribute(
    "aria-label",
    /a start event, “As data loads, after commit”/,
  );
  await expect(
    dialog.getByRole("list", { name: "The process's elements, in order" }),
  ).toContainText("Business-rule task: If a Person meets the conditions");
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  // Focus is held inside: Tab and Shift+Tab stay on Close.
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  registerCovered(REGISTRY, "open-show-as-bpmn-by-keyboard");
});

test("Escape and Close each shut the drawing and give focus back to Show as BPMN", async ({
  page,
}) => {
  await page.goto("/keyboard/rule-standards-harness.html");
  const button = page.getByRole("button", { name: "Show as BPMN" });
  await press(page, button);
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(button).toBeFocused();
  registerCovered(REGISTRY, "close-show-as-bpmn-by-escape-focus-returns");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Enter"); // on Close, which has focus
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(button).toBeFocused();
  registerCovered(REGISTRY, "close-show-as-bpmn-by-close-focus-returns");
});

test("a stored file that is not a rule's process is said so, and not drawn", async ({
  page,
}) => {
  await page.goto("/keyboard/rule-standards-harness.html?file=other");
  await press(page, page.getByRole("button", { name: "Show as BPMN" }));
  await expect(page.getByRole("status")).toContainText(
    "not a process OspreyFlow runs",
  );
  await expect(page.getByRole("img")).toHaveCount(0);
});

test("every registered Show as BPMN action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, RULE_STANDARDS_ACTIONS);
});
