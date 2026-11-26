// The GOV.UK tree's reader page by keyboard alone, with scripts on (slice GG3b; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4;
// scenario DR16). The page is read-only and its only actions are links and a film's own controls, so the cases that prove it are the
// tab order through each kind of document (every stop a native one, in the page's own order, the skip link first, the text, its marks
// and the table with no stop of their own) and that each link does what it says when activated by Enter: the way back opens the case,
// Home is Home. No `page.mouse`, no `.click()`. A picture is seen to load through the page service's own `/v1` forwarder, under the
// page's content security policy, with no violation. The service is started in the case for the `govuk` tree against fixture Conduits
// that refuse what the real routes refuse.
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

test.describe("the reader page with scripts", () => {
  test("DK1: Tab reaches the skip link, the sign-out and the ways back, in the page's order; the text, its marks and the table add no stop", async ({ page }) => {
    await withDocuments(assets, async (base) => {
      await openDocument(page, base, "k-note");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Night berth note");
      await expect(page.locator("mark")).toHaveText(["Ada Quill", "Harbour Board"]);
      const table = page.getByRole("table", { name: "Words marked in the document's text" });
      await expect(table.getByRole("columnheader")).toHaveText(["Words", "Type", "How it was marked"]);
      await expect(table.getByRole("rowheader")).toHaveText(["Ada Quill", "Harbour Board"]);
      await expect(table.getByRole("row").nth(2)).toContainText("Proposed by a model, not yet confirmed");
      expect(await tabOrder(page)).toEqual(DOCUMENT_TAB_ORDER);
    });
  });

  test("DK2: a picture loads through the forwarder under the page's policy, with no violation, and adds no stop", async ({ page }) => {
    const violations: string[] = [];
    page.on("console", (message) => {
      if (/Content Security Policy|Refused to load/i.test(message.text())) violations.push(message.text());
    });
    await withDocuments(assets, async (base) => {
      await openDocument(page, base, "k-photo");
      const picture = page.getByRole("img", { name: "A picture from the document" });
      await expect(picture).toHaveAttribute("src", `/v1/investigations/${CASE_ID}/documents/k-photo/file`);
      await expect.poll(() => picture.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBe(1);
      expect(await tabOrder(page)).toEqual(DOCUMENT_TAB_ORDER);
      expect(violations).toEqual([]);
    });
  });

  test("DK3: a film's own controls are a stop in their place; Enter on the way back opens the case, and Home is Home", async ({ page }) => {
    await withDocuments(assets, async (base) => {
      await openDocument(page, base, "k-film");
      await expect(page.locator("video[controls]")).toHaveAttribute("aria-label", "A film from the document");
      expect(await tabOrderPastControls(page)).toEqual(FILM_TAB_ORDER);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("main")).toBeFocused();
      await page.getByRole("link", { name: "Back to the case" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=${CASE_ID}$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Harbour watch");
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });
});
