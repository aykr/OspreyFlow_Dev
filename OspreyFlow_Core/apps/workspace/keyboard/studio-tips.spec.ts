// The Studio's who-can tips and its door to *Roles, teams and Authors* by keyboard alone (rule 13;
// ADR-145 Amendment 4 decision 12, L1.8): an action the person cannot take is still reached by Tab,
// says why and who can as its description, and asks the server nothing when pressed; the help page
// opens from the Studio with its way back focused, and goes back. The harness's routes refuse as the
// Conduit's do (`?rights=none` clears every right they grant), so a press that reached one would show.
import { expect, test, type Page } from "@playwright/test";

import { STUDIO_TIPS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "STUDIO_TIPS_ACTIONS";
const HARNESS = "/keyboard/ingest-studio-harness.html";

type Asked = { method: string; path: string };
const asked = (page: Page): Promise<Asked[]> =>
  page.evaluate(() => (window as unknown as { __asked: Asked[] }).__asked);

/** Tab forward until `name` has focus: the keyboard's own route to it, not a jump. */
async function tabTo(page: Page, name: string) {
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => document.activeElement?.textContent?.trim() ?? "");
    if (focused === name) return;
  }
  throw new Error(`${name} was never reached by Tab`);
}

test("a refused Studio action is reached by keyboard, says why and who can, and does nothing", async ({ page }) => {
  await page.goto(`${HARNESS}?rights=none`);
  await page.getByRole("tab", { name: "2 Sources" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: "2 Sources" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "2 Sources" }).focus();
  await tabTo(page, "Register a source");
  const register = page.getByRole("button", { name: "Register a source" });
  await expect(register).toBeFocused();
  await expect(register).toHaveAttribute("aria-disabled", "true");
  await expect(register).toHaveAccessibleDescription(
    "You need Add ingest files; the Analyst and Data Engineer roles have it. Ask an administrator to give you one.",
  );
  await page.keyboard.press("Enter");
  await page.keyboard.press("Space");
  await expect(page.getByRole("region", { name: "Register a source" })).toHaveCount(0);
  expect((await asked(page)).filter((a) => a.method !== "GET")).toEqual([]);
  registerCovered(REGISTRY, "reach-a-refused-studio-actions-tip-by-keyboard");
});

test("Roles, teams and Authors opens from the Studio by keyboard, and goes back", async ({ page }) => {
  await page.goto(HARNESS);
  const door = page.getByRole("button", { name: "Roles, teams and Authors" });
  await door.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Roles, teams and Authors" })).toBeVisible();
  const back = page.getByRole("button", { name: "← Back to the Ingest Studio" });
  await expect(back).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: "3 Pipelines" })).toBeVisible();
  registerCovered(REGISTRY, "open-roles-teams-and-authors-from-the-studio-by-keyboard");
});

test("every registered Studio tips action has its own proving test case above", () => {
  assertAllCovered("STUDIO_TIPS_ACTIONS", STUDIO_TIPS_ACTIONS);
});
