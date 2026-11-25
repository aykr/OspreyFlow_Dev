// The GOV.UK tree's page of trends shown together by keyboard alone, with scripts on (slice GR4a; `CLAUDE.md` rule 13; ADR-152
// decision 6 and I4; scenario TS11). The page is read-only and its one action of its own is the way back, so the cases that prove it are
// the tab order through the whole page (every stop a native one, in the page's own order, the skip link first, the charts and tables
// with no stop of their own) and that each link does what it says when activated by Enter. No `page.mouse`, no `.click()`.
import { expect, test } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { TRENDS_TAB_ORDER, openTrends, withTrends } from "../packTrendsServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

test.describe("trends shown together with scripts", () => {
  test("TK1: Tab reaches the skip link, the sign-out and the way back, in the page's order, and the charts and tables add no stop", async ({ page }) => {
    await withTrends(assets, async (base) => {
      await openTrends(page, base);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Trends shown together");
      await expect(page.getByRole("heading", { level: 2 })).toHaveText(["Harbour meetings"]);
      await expect(page.getByRole("img", { name: /^Harbour meetings: one bar for each of/ })).toHaveCount(1);
      expect(await tabOrder(page)).toEqual(TRENDS_TAB_ORDER);
    });
  });

  test("TK2: the skip link takes focus to the main landmark, and Enter on the way back goes Home", async ({ page }) => {
    await withTrends(assets, async (base) => {
      await openTrends(page, base);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/#main$/);
      await expect(page.getByRole("main")).toBeFocused();
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });

  test("TK3: each trend's figures are a table a reader can move through by its headers, after its chart", async ({ page }) => {
    await withTrends(assets, async (base) => {
      await openTrends(page, base);
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      const table = page.getByRole("table", { name: "The figures of Harbour meetings" });
      await expect(table.getByRole("columnheader")).toHaveText(["Week starting", "Count"]);
      await expect(table.getByRole("rowheader")).toHaveText(["5 October 2026", "12 October 2026", "19 October 2026", "26 October 2026"]);
      await expect(page.getByText("Some items of this pack are not shown to you")).toHaveCount(1);
    });
  });
});
