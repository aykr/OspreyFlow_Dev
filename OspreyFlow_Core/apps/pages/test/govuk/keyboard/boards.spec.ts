// The GOV.UK tree's boards page by keyboard alone, with scripts on (slice GG4a; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4; scenario
// BD14), and its three writes (slice GG4c; BD28: one case for each of making, sharing and deleting). For a reader offered no write the
// page's only actions are links, so the cases that prove it are the tab order through each page (every stop a native one, in the page's
// own order, the skip link first, the tables with no stop of their own) and that each link does what it says when activated by Enter: a board's name opens it, the way back returns to the case's boards and then to the case, Home is Home
// (the case's own link to its boards, followed here too, is also `cases.spec.ts` CK2's). No `page.mouse`, no `.click()`. The service is started in the case for the `govuk` tree against a fixture
// Conduit that refuses what the real routes refuse.
import { expect, test } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { BOARD_TAB_ORDER, CONFIRM_TAB_ORDER, DRAWS, DRAW_BOARD_TAB_ORDER, DRAW_LIST_TAB_ORDER, EMPTY_PATH, LIST_TAB_ORDER, openBoards, withBoards } from "../boardsServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

/** Tab, from wherever the page starts, until the target holds the focus: by the keyboard alone, never by a script's focus. */
async function tabTo(page: Page, target: Locator): Promise<void> {
  for (let i = 0; i < 40; i += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => element === document.activeElement)) return;
  }
  throw new Error("Tab never reached the target");
}

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
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Harbour watch");
      // And from the case's page, its link to its boards brings the reader back to them.
      await page.getByRole("link", { name: "Drawing boards in this case" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Drawing boards in this case");
    });
  });

  test("BK3: the landmarks are there, and each table is one a reader can move through by its headers", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base, "/cases/boards?case=k-harbour&board=k-quay");
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      const drawn = page.getByRole("table", { name: "Drawn items on this board" });
      await expect(drawn.getByRole("columnheader")).toHaveText(["Item", "Type", "Marking", "Grading"]);
      await expect(page.getByRole("table", { name: "Links on this board" }).getByRole("columnheader")).toHaveText(["Link", "Type", "From", "To", "Drawn or loaded", "Marking", "Grading"]);
      await expect(drawn.getByRole("rowheader")).toHaveText([/^Tall man\s*Drawn, not loaded$/]);
      const loaded = page.getByRole("table", { name: "Loaded items on this board" });
      await expect(loaded.getByRole("rowheader")).toHaveText([/^Evening Tide\s*A dataset this case reads: a live reference, not editable here$/]);
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });

  // Slice GG4c: each write, by keyboard alone from the page's own tab order, to the page the write leads to.
  test("BK4: a board is made by keyboard: a wrong name is said, its link goes to the field, and Enter makes the board", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base);
      expect(await tabOrder(page)).toEqual(DRAW_LIST_TAB_ORDER);
      await openBoards(page, base);
      await tabTo(page, page.getByRole("button", { name: "Make a blank board" }));
      await page.keyboard.press("Enter");
      await expect(page.getByRole("alert")).toContainText("There is a problem");
      await tabTo(page, page.getByRole("link", { name: "Enter a board name of 1 to 200 characters" }));
      await page.keyboard.press("Enter");
      // A link to a field's own id puts the focus on the field, with no script.
      const field = page.getByRole("textbox", { name: "Board name" });
      await expect(field).toBeFocused();
      await page.keyboard.type("Supply routes");
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "Make a blank board" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases/boards\\?case=k-harbour&board=b-made-1$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Supply routes");
    }, DRAWS);
  });

  test("BK5: a board is shared by keyboard: Enter on Share with the case shows it shared, with no share left to press", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base, EMPTY_PATH);
      expect(await tabOrder(page)).toEqual(DRAW_BOARD_TAB_ORDER);
      await openBoards(page, base, EMPTY_PATH);
      await expect(page.getByText("Sharing cannot be undone.")).toBeVisible();
      await tabTo(page, page.getByRole("button", { name: "Share with the case" }));
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases/boards\\?case=k-harbour&board=k-empty$`));
      await expect(page.getByRole("definition").first()).toHaveText("Shared with the case");
      await expect(page.getByRole("button", { name: "Share with the case" })).toHaveCount(0);
    }, DRAWS);
  });

  test("BK6: a board is deleted by keyboard: its link asks first, Enter on Delete board deletes it, and the boards say so", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base, EMPTY_PATH);
      await tabTo(page, page.getByRole("link", { name: "Delete this board" }));
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Delete this board?");
      expect(await tabOrder(page)).toEqual(CONFIRM_TAB_ORDER);
      await openBoards(page, base, `${EMPTY_PATH}&delete=confirm`);
      await tabTo(page, page.getByRole("button", { name: "Delete board" }));
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases/boards\\?case=k-harbour$`));
      await expect(page.getByRole("alert")).toContainText("The board was deleted. What was drawn on it stays in the case.");
      await expect(page.getByRole("link", { name: "Empty start" })).toHaveCount(0);
    }, DRAWS);
  });
});
