// A scripted, keyboard-only walkthrough of the three setup screens — `06_DECISIONS.md` ADR-049
// Stage 2 §6 amendment 21, proving reachability end to end for this surface's own first three
// keyboard-driven actions. Like `apps/workspace/keyboard/*.spec.ts`, this test never calls
// `page.mouse`/`.click()`. Against the real `harness.webapp` server (this directory's own
// `playwright.config.ts` starts it) and a real `PUT /api/config`, not a mocked response.
import { expect, test } from "@playwright/test";

import { assertAllCovered, registerCovered, SETUP_SCREENS_ACTIONS } from "./actions";

test("Tab reaches the Profile screen's own options and a real keyboard Enter saves it", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("radio", { name: /local-lite/ }).waitFor();

  // Starting focus is the document body — proving Tab actually reaches each control, the same
  // discipline every spec in `apps/workspace/keyboard/` already follows.
  await page.keyboard.press("Tab"); // Profile nav button
  await expect(page.getByRole("button", { name: "Profile", exact: true })).toBeFocused();
  await page.keyboard.press("Tab"); // Components nav button
  await page.keyboard.press("Tab"); // Models nav button
  await page.keyboard.press("Tab"); // the radio group (one tab stop, lands on the checked radio)
  await expect(page.getByRole("radio", { name: /local-lite/ })).toBeFocused();
  await page.keyboard.press("ArrowDown"); // moves selection to "small" within the radio group
  await expect(page.getByRole("radio", { name: /^small/ })).toBeChecked();
  await page.keyboard.press("Tab"); // Tab exits the radio group as a whole, straight to Save
  await expect(page.getByRole("button", { name: "Save profile" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);
  await expect(page.getByText("Profile", { exact: false }).first()).toBeVisible();
  await expect(page.locator(".summary-rail").getByText("decided")).toBeVisible();

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-profile");
});

test("a keyboard-activated screen switch reaches Components and a real Enter saves it", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Components", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("combobox", { name: "Graph store" }).waitFor();

  // Activating "Components" leaves focus on that nav button itself (Enter on a button never
  // moves focus away from it) — the next Tab reaches the last nav button ("Models"), still in
  // the DOM after it, and only the one after that reaches the newly-rendered screen's own field.
  await page.keyboard.press("Tab"); // Models nav button
  await page.keyboard.press("Tab"); // graph store select
  await expect(page.getByRole("combobox", { name: "Graph store" })).toBeFocused();
  await page.keyboard.press("Tab"); // analytics engine select
  await expect(page.getByRole("combobox", { name: "Analytics engine" })).toBeFocused();
  await page.keyboard.press("Tab"); // Save components button
  await expect(page.getByRole("button", { name: "Save components" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-components");
});

test("a keyboard-activated screen switch reaches Models and a real Enter saves it", async ({
  page,
}) => {
  await page.goto("/keyboard/setup-harness.html");
  await page.getByRole("button", { name: "Models", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("checkbox", { name: /Local only/ }).waitFor();

  await page.keyboard.press("Tab"); // the "local only" checkbox
  await expect(page.getByRole("checkbox", { name: /Local only/ })).toBeFocused();
  await page.keyboard.press("Tab"); // Save models button (hosted-fallback fields hidden while local only)
  await expect(page.getByRole("button", { name: "Save models" })).toBeFocused();

  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/api/config") && r.request().method() === "PUT"),
    page.keyboard.press("Enter"),
  ]);
  expect(response.ok()).toBe(true);

  registerCovered("SETUP_SCREENS_ACTIONS", "submit-save-models");
});

test("every registered setup-screen action has its own proving test case above", () => {
  assertAllCovered("SETUP_SCREENS_ACTIONS", SETUP_SCREENS_ACTIONS);
});
