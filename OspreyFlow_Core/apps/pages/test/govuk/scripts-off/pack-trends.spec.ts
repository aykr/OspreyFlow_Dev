// The GOV.UK tree's page of trends shown together with scripts switched off (slice GR4a; ADR-152 decision 6 and invariant I4;
// `CLAUDE.md` rule 13; scenario TS12): the same page, every trend with its chart and table, the same stops in the same order, and each
// stop still does what it says, because the page needs no script. `../keyboard/pack-trends.spec.ts` is the same walk with scripts on.
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
test.use({ javaScriptEnabled: false });

test.describe("trends shown together with scripts switched off", () => {
  test("TO1: the page is whole, each trend with its chart and its table, and its stops come in the same order", async ({ page }) => {
    await withTrends(assets, async (base) => {
      await openTrends(page, base);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Trends shown together");
      await expect(page.getByRole("img", { name: /^Harbour meetings: one bar for each of/ })).toHaveCount(1);
      await expect(page.getByRole("table", { name: "The figures of Harbour meetings" }).getByRole("row")).toHaveCount(5);
      await expect(page.getByText("Some items of this pack are not shown to you")).toHaveCount(1);
      await expect(page.getByText("A note that is not a trend.")).toHaveCount(0);
      expect(await tabOrder(page)).toEqual(TRENDS_TAB_ORDER);
    });
  });

  test("TO2: the skip link and the way back work by Enter with no script", async ({ page }) => {
    await withTrends(assets, async (base) => {
      await openTrends(page, base);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/#main$/);
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });
});
