// The GOV.UK tree's boards page with scripts switched off (slice GG4a; ADR-152 decision 6 and invariant I4; `CLAUDE.md` rule 13; scenario
// BD15), and its three writes (slice GG4c; BD29): the same pages, the same stops in the same order, and each link and form still does
// what it says, because the page needs no script.
// `../keyboard/boards.spec.ts` is the same walk with scripts on.
import { expect, test } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { BOARD_TAB_ORDER, DRAWS, DRAW_LIST_TAB_ORDER, EMPTY_PATH, LIST_TAB_ORDER, QUAY_PATH, openBoards, withBoards } from "../boardsServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});
test.use({ javaScriptEnabled: false });

test.describe("the boards page with scripts switched off", () => {
  test("BO1: both pages are complete and their stops come in the same order", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base);
      await expect(page.getByRole("table", { name: "Drawing boards in this case" }).getByRole("row")).toHaveCount(3);
      expect(await tabOrder(page)).toEqual(LIST_TAB_ORDER);
      await openBoards(page, base, QUAY_PATH);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Quay sketch");
      await expect(page.getByRole("table", { name: "Drawn items on this board" })).toBeVisible();
      await expect(page.getByRole("table", { name: "Loaded items on this board" })).toBeVisible();
      await expect(page.getByRole("table", { name: "Links on this board" })).toBeVisible();
      expect(await tabOrder(page)).toEqual(BOARD_TAB_ORDER);
    });
  });

  test("BO2: a board's link and every way back work by Enter with no script", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base);
      await page.getByRole("link", { name: "Empty start" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Empty start");
      await expect(page.getByText("No items are shown on this board.")).toBeVisible();
      await page.getByRole("link", { name: "Back to this case's boards" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Drawing boards in this case");
      await page.getByRole("link", { name: "Back to this case" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Harbour watch");
      await page.getByRole("link", { name: "Drawing boards in this case" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Drawing boards in this case");
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });

  test("BO3: a board is made, shared and deleted by its forms, each by Enter, with no script", async ({ page }) => {
    await withBoards(assets, async (base) => {
      await openBoards(page, base);
      expect(await tabOrder(page)).toEqual(DRAW_LIST_TAB_ORDER);
      await page.getByRole("textbox", { name: "Board name" }).focus();
      await page.keyboard.type("Supply routes");
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Supply routes");
      await openBoards(page, base, EMPTY_PATH);
      await page.getByRole("button", { name: "Share with the case" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("definition").first()).toHaveText("Shared with the case");
      await page.getByRole("link", { name: "Delete this board" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Delete this board?");
      await page.getByRole("button", { name: "Delete board" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("alert")).toContainText("The board was deleted.");
      await expect(page.getByRole("link", { name: "Supply routes" })).toBeVisible();
      await expect(page.getByRole("link", { name: "Empty start" })).toHaveCount(0);
    }, DRAWS);
  });
});
