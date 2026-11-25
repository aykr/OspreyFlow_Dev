// The GOV.UK tree's boards page by keyboard alone, with scripts on (slice GG4a; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4; scenario
// BD14). The page is read-only and its only actions are links, so the cases that prove it are the tab order through each page (every
// stop a native one, in the page's own order, the skip link first, the tables with no stop of their own) and that each link does what it
// says when activated by Enter: a board's name opens it, the way back returns to the case's boards and then to the case, Home is Home
// (the case's own link to its boards is `cases.spec.ts` CK2's). No `page.mouse`, no `.click()`. The service is started in the case for the `govuk` tree against a fixture
// Conduit that refuses what the real routes refuse.
import { expect, test } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { BOARD_TAB_ORDER, LIST_TAB_ORDER, openBoards, withBoards } from "../boardsServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

test.describe("the boards page with scripts", () => {
  test("BK1: Tab reaches the skip link, the sign-out, each board's link and the ways back, in the page's order; the table adds no stop", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Drawing boards in this case");
      await expect(page.getByRole("table", { name: "Drawing boards in this case" }).getByRole("row")).toHaveCount(3);
      expect(await tabOrder(page)).toEqual(LIST_TAB_ORDER);
    });
  });

  test("BK2: Enter on a board's name opens it; its stops come in order; Enter on the ways back returns to the boards, then the case", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("main")).toBeFocused();
      await page.getByRole("link", { name: "Quay sketch" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases/boards\\?case=k-harbour&board=k-quay$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Quay sketch");
      await expect(page.getByRole("table", { name: "Links on this board" }).getByRole("rowheader")).toHaveText(["Boards at night"]);
      expect(await tabOrder(page)).toEqual(BOARD_TAB_ORDER);
      await page.getByRole("link", { name: "Back to this case's boards" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases/boards\\?case=k-harbour$`));
      await page.getByRole("link", { name: "Back to this case" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=k-harbour$`));
    });
  });

  test("BK3: the landmarks are there, and each table is one a reader can move through by its headers", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base, "/cases/boards?case=k-harbour&board=k-quay");
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      const drawn = page.getByRole("table", { name: "Drawn on this board" });
      await expect(drawn.getByRole("columnheader")).toHaveText(["Item", "Type", "Marking", "Grading", "Source"]);
      await expect(drawn.getByRole("rowheader")).toHaveText([/^Tall man\s*Drawn, not loaded$/]);
      const loaded = page.getByRole("table", { name: "Loaded items on this board" });
      await expect(loaded.getByRole("rowheader")).toHaveText([/^Evening Tide\s*A dataset this case reads: a live reference, not editable here$/]);
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });
});
