// The GOV.UK tree's cases page with scripts switched off (slices GR1a and GR1e; ADR-152 decision 6 and invariant I4; `CLAUDE.md` rule 13;
// scenario CS13 and CS25): the same pages, the same stops in the same order, and each link still does what it says, because the page needs no script.
// `../keyboard/cases.spec.ts` is the same walk with scripts on.
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
test.use({ javaScriptEnabled: false });

test.describe("the cases page with scripts switched off", () => {
  test("CO1: both pages are complete and their stops come in the same order", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base);
      await expect(page.getByRole("table", { name: "Your cases" }).getByRole("row")).toHaveCount(3);
      expect(await tabOrder(page)).toEqual(LIST_TAB_ORDER);
      await openCases(page, base, "/cases?case=k-harbour");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Harbour watch");
      await expect(page.getByText("A saved trend")).toBeVisible();
      expect(await tabOrder(page)).toEqual(CASE_TAB_ORDER);
    });
  });

  test("CO2: a case's link and the ways back work by Enter with no script", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base);
      await page.getByRole("link", { name: "Ferry routes" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ferry routes");
      await expect(page.getByText("This case has no brief yet.")).toBeVisible();
      await page.getByRole("link", { name: "Back to your cases" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Your cases");
    });
  });

  test("CO3: the contents' History works by Enter with no script, and a case with no step says so", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base, "/cases?case=k-harbour");
      await page.getByRole("link", { name: "History" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=k-harbour#history$`));
      await expect(page.locator(":target")).toHaveText("History");
      await expect(page.getByRole("table", { name: "Changes to this case, oldest first" }).getByRole("rowheader")).toHaveText(["Seeded", "Edited the brief"]);
      await openCases(page, base, "/cases?case=k-ferry");
      await expect(page.getByText("Nothing has changed in this case yet.")).toBeVisible();
      expect(await tabOrder(page)).toEqual(CASE_TAB_ORDER);
    });
  });
});
