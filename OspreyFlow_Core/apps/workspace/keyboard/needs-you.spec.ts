// *Needs you* by keyboard alone (ADR-145 decision 11, A2; L2.7; `CLAUDE.md` rule 13): the top bar's
// control opened, each entry's tip read with it as it takes focus, an overdue promotion opening Admin's
// Operations and a dataset's proposals its Model tab, Escape giving focus back; and in the Studio, the
// reminder above the other tabs opening *1 Model · n proposed*. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { NEEDS_YOU_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "NEEDS_YOU_ACTIONS";
const HARNESS = "/keyboard/needs-you-harness.html";

async function openPanel(page: Page) {
  const button = page.getByRole("button", { name: /^Needs you · 3/ });
  await button.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Needs you" })).toBeVisible();
}

function opened(page: Page): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { __opened: string[] }).__opened);
}

test("Needs you opens, each entry's tip is read with it, and Escape gives focus back", async ({ page }) => {
  await page.goto(HARNESS);
  await openPanel(page);
  await page.keyboard.press("Tab");
  const first = page.getByRole("button", { name: /Promotion SYN-load-7/ });
  await expect(first).toBeFocused();
  await expect(first).toHaveAccessibleDescription(/waited past the days your administrator set/);
  await page.keyboard.press("Tab");
  const proposals = page.getByRole("button", { name: /2 proposed link types to decide in Harbour/ });
  await expect(proposals).toBeFocused();
  await expect(proposals).toHaveAccessibleDescription(/add each to the draft model or decline it/);
  await page.keyboard.press("Tab");
  const above = page.getByText("A proposed link type in Border watch (synthetic) is above your clearance");
  await expect(above).toBeFocused();
  await expect(above).toHaveAccessibleDescription(/told only that it exists/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("group", { name: "Needs you" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Needs you · 3/ })).toBeFocused();
  registerCovered(REGISTRY, "read-a-needs-you-entrys-tip-by-keyboard");
});

test("an overdue promotion opens Operations, and a dataset's proposals its Model tab, by keyboard", async ({ page }) => {
  await page.goto(HARNESS);
  await openPanel(page);
  await page.getByRole("button", { name: /Promotion SYN-load-7/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Needs you" })).toHaveCount(0);
  expect(await opened(page)).toEqual(["operations"]);
  registerCovered(REGISTRY, "open-operations-from-needs-you-by-keyboard");
  await openPanel(page);
  await page.getByRole("button", { name: /2 proposed link types to decide in Harbour/ }).focus();
  await page.keyboard.press("Enter");
  expect(await opened(page)).toEqual(["operations", "model:SYN-ds-a"]);
  registerCovered(REGISTRY, "open-a-datasets-model-tab-from-needs-you-by-keyboard");
});

test("the Studio's reminder opens 1 Model · n proposed by keyboard, its tip read with it", async ({ page }) => {
  await page.goto("/keyboard/ingest-studio-harness.html?proposed=1");
  const reminder = page.getByRole("button", { name: "2 proposed link types wait for you on the Model tab." });
  await reminder.focus();
  await expect(reminder).toHaveAccessibleDescription(/Decide them on 1 Model/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: "1 Model · 2 proposed" })).toHaveAttribute("aria-selected", "true");
  await expect(reminder).toHaveCount(0);
  registerCovered(REGISTRY, "open-the-model-tab-from-the-studios-reminder-by-keyboard");
});

// ADR-145 Amendment 4 decision 12 (L2.7): Home's What you can do, and what you answer for, by keyboard:
// each line's why read with it, a case, a Model tab and Operations opened, and Why can I do this? opened.
test("what you answer for opens where to act, its why read with each line, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/answers-harness.html");
  const author = page.getByRole("button", { name: "Author of Harbour wing review" });
  await author.focus();
  await expect(author).toHaveAccessibleDescription(/^Why: Answers for the case/);
  await page.keyboard.press("Enter");
  const model = page.getByRole("button", { name: /2 proposed link types to decide/ });
  await model.focus();
  await expect(model).toHaveAccessibleDescription("Why: Given by your Data Engineer role.");
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: /^Reviewer of promotions/ }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => (window as unknown as { __opened: string[] }).__opened)).toEqual([
    "case:SYN-c1", "model:SYN-ds-a", "operations",
  ]); // prettier-ignore
  await expect(page.getByRole("button", { name: /Border watch/ })).toHaveCount(0);
  registerCovered(REGISTRY, "open-what-you-answer-for-by-keyboard");
  const byPlace = page.getByText("What you can do, by place");
  await byPlace.focus();
  await page.keyboard.press("Enter");
  const why = page.getByText(/^Review promotions:/);
  await why.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Given by your Data Engineer role.").first()).toBeVisible();
  registerCovered(REGISTRY, "read-why-i-can-do-this-by-keyboard");
});

test("every registered Needs you action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, NEEDS_YOU_ACTIONS);
});
