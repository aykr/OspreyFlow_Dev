// The GOV.UK tree's Help page by keyboard alone, with scripts on (slice GR2a; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4; scenario HP5).
// The page has no action of its own beyond links, so the cases that prove it are the tab order through the whole page (every stop a
// native one, in the page's own order, the skip link first), that each stop does what it says when activated by Enter, and that the
// landmarks are there for a reader who moves by them. No `page.mouse`, no `.click()`. The same flows with scripts switched off are
// `../scripts-off/help.spec.ts`.
import { expect, test } from "@playwright/test";

import { HELP_TAB_ORDER, buildScratchAssets, openHelp, startGovuk, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets, Govuk } from "../helpServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

async function withService(run: (service: Govuk) => Promise<void>): Promise<void> {
  const service = await startGovuk(assets);
  try {
    await run(service);
  } finally {
    await service.stop();
  }
}

test.describe("the Help page with scripts", () => {
  test("HK1: Tab reaches the skip link first, then the sign-out, each section's link and the way back, in the page's order", async ({ page }) => {
    await withService(async (s) => {
      await openHelp(page, s.base);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Help");
      expect(await tabOrder(page)).toEqual(HELP_TAB_ORDER);
    });
  });

  test("HK2: the skip link takes focus to the main landmark, and the next Tab is the first link inside it", async ({ page }) => {
    await withService(async (s) => {
      await openHelp(page, s.base);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/#main$/);
      await expect(page.getByRole("main")).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "The places" })).toBeFocused();
    });
  });

  test("HK3: Enter on a section's link goes to that section, and Enter on the way back goes to Home", async ({ page }) => {
    await withService(async (s) => {
      await openHelp(page, s.base);
      await page.getByRole("link", { name: "What each right lets you do" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/#help-rights$/);
      await expect(page.getByRole("heading", { level: 2, name: "What each right lets you do" })).toBeInViewport();
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${s.base}/$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });

  test("HK4: the landmarks are there, and the roles and the rights are tables a reader can move through by their headers", async ({ page }) => {
    await withService(async (s) => {
      await openHelp(page, s.base);
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      await expect(page.getByRole("navigation", { name: "On this page" })).toHaveCount(1);
      const roles = page.getByRole("table", { name: "The built-in roles, what each is for and the places it opens" });
      await expect(roles.getByRole("columnheader")).toHaveText(["Role", "What it is for", "Places it opens"]);
      await expect(roles.getByRole("rowheader").first()).toBeVisible();
      const rights = page.getByRole("table", { name: "Each right, and what it lets a person do" });
      await expect(rights.getByRole("columnheader")).toHaveText(["Right", "What it lets you do"]);
    });
  });
});
