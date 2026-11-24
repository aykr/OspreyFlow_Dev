// The GOV.UK tree's Help page with scripts switched off (slice GR2a; ADR-152 decision 6 and invariant I4; `CLAUDE.md` rule 13;
// scenario HP5): the same page, the same stops in the same order, and each stop still does what it says, because the page needs no
// script. `../keyboard/help.spec.ts` is the same walk with scripts on.
import { expect, test } from "@playwright/test";

import { HELP_TAB_ORDER, buildScratchAssets, openHelp, startGovuk, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});
test.use({ javaScriptEnabled: false });

test.describe("the Help page with scripts switched off", () => {
  test("HO1: the page is complete and its stops come in the same order", async ({ page }) => {
    const s = await startGovuk(assets);
    try {
      await openHelp(page, s.base);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Help");
      await expect(page.getByRole("table", { name: "The built-in roles, what each is for and the places it opens" }).getByRole("row")).not.toHaveCount(1);
      await expect(page.getByRole("table", { name: "Each right, and what it lets a person do" }).getByRole("row")).not.toHaveCount(1);
      expect(await tabOrder(page)).toEqual(HELP_TAB_ORDER);
    } finally {
      await s.stop();
    }
  });

  test("HO2: the skip link, a section's link and the way back work by Enter with no script", async ({ page }) => {
    const s = await startGovuk(assets);
    try {
      await openHelp(page, s.base);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/#main$/);
      await page.getByRole("link", { name: "Teams, leads and Authors" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/#help-teams$/);
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    } finally {
      await s.stop();
    }
  });
});
