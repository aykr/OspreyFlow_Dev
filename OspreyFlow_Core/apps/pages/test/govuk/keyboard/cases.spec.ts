// The GOV.UK tree's cases page by keyboard alone, with scripts on (slices GR1a and GR1e; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4;
// scenario CS12 and CS25). The page is read-only and its only actions are links, so the cases that prove it are the tab order through each page (every
// stop a native one, in the page's own order, the skip link first, the table with no stop of its own) and that each link does what it
// says when activated by Enter: a case's name opens its page, the way back returns to the list, Home is Home. No `page.mouse`, no
// `.click()`. The service is started in the case for the `govuk` tree against a fixture Conduit that refuses what the real routes refuse.
import { expect, test } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { CASE_TAB_ORDER, LIST_TAB_ORDER, openCases, withCases } from "../casesServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

test.describe("the cases page with scripts", () => {
  test("CK1: Tab reaches the skip link, the sign-out, each case's link and the way back, in the page's order; the table adds no stop", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Your cases");
      await expect(page.getByRole("table", { name: "Your cases" }).getByRole("row")).toHaveCount(3);
      expect(await tabOrder(page)).toEqual(LIST_TAB_ORDER);
    });
  });

  test("CK2: Enter on a case's name opens its page; its stops come in order; Enter on the way back returns to the list, and Home is Home", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("main")).toBeFocused();
      await page.getByRole("link", { name: "Harbour watch" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=k-harbour$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Harbour watch");
      await expect(page.getByText("Which vessels berth after dark?")).toBeVisible();
      expect(await tabOrder(page)).toEqual(CASE_TAB_ORDER);
      await page.getByRole("link", { name: "Back to your cases" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases$`));
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });

  test("CK4: Enter on the contents' History takes the reader to the history, a table of the steps with no stop of its own", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base, "/cases?case=k-harbour");
      await page.getByRole("link", { name: "History" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=k-harbour#history$`));
      await expect(page.locator(":target")).toHaveText("History");
      const table = page.getByRole("table", { name: "Changes to this case, oldest first" });
      await expect(table).toBeInViewport();
      await expect(table.getByRole("columnheader")).toHaveText(["Step", "When", "Restore"]);
      await expect(table.getByRole("rowheader")).toHaveText(["Seeded", "Edited the brief"]);
      await expect(table.getByRole("row").last()).toContainText("Cannot be restored");
      // The next stop after the part is the way back: the history holds none of its own.
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Back to your cases" })).toBeFocused();
    });
  });

  test("CK3: the landmarks are there, and the cases are a table a reader can move through by its headers", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base);
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      const table = page.getByRole("table", { name: "Your cases" });
      await expect(table.getByRole("columnheader")).toHaveText(["Case", "Your level", "Domains", "Datasets", "Made"]);
      await expect(table.getByRole("rowheader")).toHaveText(["Harbour watch", /^Ferry routes\s*You closed this case's tab$/]);
    });
  });
});
