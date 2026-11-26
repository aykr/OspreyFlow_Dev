// The GOV.UK tree's reader page with scripts switched off (slice GG3b; ADR-152 decision 6 and invariant I4; `CLAUDE.md` rule 13;
// scenario DR16): the same pages, the same stops in the same order, a picture still loaded, and each link still does what it says,
// because the page needs no script. `../keyboard/document.spec.ts` is the same walk with scripts on.
import { expect, test } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { CASE_ID, DOCUMENT_TAB_ORDER, FILM_TAB_ORDER, openDocument, tabOrderPastControls, withDocuments } from "../documentServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});
test.use({ javaScriptEnabled: false });

test.describe("the reader page with scripts switched off", () => {
  test("DO1: each kind of document is complete and its stops come in the same order", async ({ page }) => {
    await withDocuments(assets, async (base) => {
      await openDocument(page, base, "k-note");
      await expect(page.locator("mark")).toHaveText(["Ada Quill", "Harbour Board"]);
      await expect(page.getByRole("table", { name: "Words marked in the document's text" }).getByRole("row")).toHaveCount(3);
      expect(await tabOrder(page)).toEqual(DOCUMENT_TAB_ORDER);
      await openDocument(page, base, "k-photo");
      await expect.poll(() => page.getByRole("img", { name: "A picture from the document" }).evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBe(1);
      expect(await tabOrder(page)).toEqual(DOCUMENT_TAB_ORDER);
      await openDocument(page, base, "k-film");
      expect(await tabOrderPastControls(page)).toEqual(FILM_TAB_ORDER);
    });
  });

  test("DO2: the way back to the case and the way Home work by Enter with no script", async ({ page }) => {
    await withDocuments(assets, async (base) => {
      await openDocument(page, base, "k-note");
      await page.getByRole("link", { name: "Back to the case" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=${CASE_ID}$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Harbour watch");
      await page.goBack();
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });
});
