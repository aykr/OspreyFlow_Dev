// The saved views panel by keyboard alone, and under axe in the three looks (ADR-145 Amendment 17, the owner's
// exception of 14 November 2026; rule 13). The panel is the real `ViewsPanel` in the real drawer, titled *Saved
// views* as `App.tsx` draws it from the case line (`saved-views-panel-harness.tsx`). Its list starts with *The
// whole case*, marked *Open now* while no saved view is open; the saved view open now is marked so and offers no
// *Open*; a view saved under the default name says its first item and when it was saved. Each control is reached by
// Tab from the panel and pressed with Enter; the drawer then closes and focus goes back to *Saved views*. No
// `page.mouse`, no `.click()`.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { checkUndecidedContrast } from "../a11y/undecidedContrast";
import { SAVED_VIEWS_PANEL_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "SAVED_VIEWS_PANEL_ACTIONS";
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
type Look = "dark" | "light" | "govuk";

async function open(page: Page, query = "", look: Look = "dark"): Promise<void> {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const parts = [query, look === "govuk" ? "brand=govuk" : ""].filter(Boolean).join("&");
  await page.goto(`/keyboard/saved-views-panel-harness.html${parts ? `?${parts}` : ""}`);
  if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  const drawer = page.getByRole("dialog", { name: "Saved views" });
  await expect(drawer).toBeVisible();
  // The list inside it, by its own name (a summary list under GOV.UK, a list otherwise), drawn once the Conduit answers.
  await expect(drawer.getByLabel("Saved views", { exact: true })).toBeVisible();
}

const row = (page: Page, id: string) => page.locator(`[data-view-id="${id}"]`);
const opened = (page: Page) => page.evaluate(() => window.__SAVED_VIEWS__!.opened);

/** Tab from where focus is, within the panel, until `name` has it, then Enter. */
async function tabTo(page: Page, name: string): Promise<void> {
  const target = page.getByRole("button", { name, exact: true });
  for (let i = 0; i < 25 && !(await target.evaluate((el) => el === document.activeElement)); i += 1) await page.keyboard.press("Tab");
  await expect(target, `${name} was not reached by Tab`).toBeFocused();
  await page.keyboard.press("Enter");
}

test("a saved view is opened from the panel by keyboard, and focus goes back to Saved views", async ({ page }) => {
  await open(page);
  await expect(row(page, "whole-case")).toContainText("Open now");
  await tabTo(page, "Open Selection of 3 nodes");
  await expect.poll(() => opened(page)).toEqual(["v-3"]);
  await expect(page.getByRole("dialog", { name: "Saved views" })).toHaveCount(0);
  await expect(page.locator("[data-saved-views-button]")).toBeFocused();
  registerCovered(REGISTRY, "open-a-saved-view-from-the-panel-by-keyboard");
});

test("the whole case is opened from the panel by keyboard while a saved view is open, and focus goes back", async ({ page }) => {
  await open(page, "open=v-3");
  // The saved view open now is marked so, and its Open is not there to reach; the whole case is offered.
  await expect(row(page, "v-3")).toContainText("Open now");
  await expect(row(page, "v-3").getByRole("button", { name: "Open Selection of 3 nodes" })).toHaveCount(0);
  await expect(row(page, "whole-case")).not.toContainText("Open now");
  await tabTo(page, "Open the whole case");
  await expect.poll(() => opened(page)).toEqual(["whole-case"]);
  await expect(page.locator("#lens")).toHaveText("Whole case");
  await expect(page.locator("[data-saved-views-button]")).toBeFocused();
  registerCovered(REGISTRY, "open-the-whole-case-from-the-panel-by-keyboard");
});

test("a view saved under the default name says its first item and when it was saved; a named one does not", async ({ page }) => {
  await open(page);
  await expect(row(page, "v-3")).toContainText("Tarbuck, Kyle · saved 14 Nov 2026, 12:01");
  await expect(row(page, "v-2")).toContainText("Vance, Callum · saved 14 Nov 2026, 11:40");
  await expect(row(page, "v-hidden")).toContainText("Saved 13 Nov 2026, 09:15");
  await expect(row(page, "v-named")).not.toContainText("PIN-Z2486");
});

for (const look of ["dark", "light", "govuk"] as const) {
  for (const [state, query] of [["with the whole case open", ""], ["with a saved view open", "open=v-3"]] as const) {
    test(`the saved views panel, ${state}, has no automated WCAG 2.2 A or AA violation (${look})`, async ({ page }) => {
      await open(page, query, look);
      if (look === "light") await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
      if (look === "govuk") await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
      const results = await new AxeBuilder({ page }).include(".drawer").withTags(WCAG_TAGS).analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      const contrast = await checkUndecidedContrast(page, results);
      expect(contrast.unlisted, "colour contrast axe left undecided").toEqual([]);
    });
  }
}

test("every registered saved views panel action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, SAVED_VIEWS_PANEL_ACTIONS);
});
