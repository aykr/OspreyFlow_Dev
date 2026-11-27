// The GOV.UK tree's cases page with scripts switched off (slices GR1a and GR1e; ADR-152 decision 6 and invariant I4; `CLAUDE.md` rule 13;
// scenario CS13 and CS25): the same pages, the same stops in the same order, and each link still does what it says, because the page needs no script.
// `../keyboard/cases.spec.ts` is the same walk with scripts on. New case (slice GR1b; scenario CS41): every field is shown and the form
// posts with no script.
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

  test("CO3: each of the contents' links works by Enter with no script, and a case with no step says so", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base, "/cases?case=k-harbour");
      for (const [name, part] of [["About this case", "about"], ["Brief", "brief"]] as const) {
        await page.getByRole("link", { name, exact: true }).focus();
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=k-harbour#${part}$`));
        await expect(page.locator(":target")).toHaveText(name);
      }
      await page.getByRole("link", { name: "History" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=k-harbour#history$`));
      await expect(page.locator(":target")).toHaveText("History");
      await expect(page.getByRole("table", { name: "Changes to this case, in the order the case records them" }).getByRole("rowheader")).toHaveText(["Seeded", "Edited the brief"]);
      await openCases(page, base, "/cases?case=k-ferry");
      await expect(page.getByText("Nothing has changed in this case yet.")).toBeVisible();
      expect(await tabOrder(page)).toEqual(CASE_TAB_ORDER);
    });
  });

  test("CO4 (CS41): with no script every field of New case is shown, and a case is made", async ({ page }) => {
    await withCases(
      assets,
      async (base) => {
        await openCases(page, base);
        await page.getByRole("link", { name: "New case" }).focus();
        await page.keyboard.press("Enter");
        await expect(page.getByRole("textbox", { name: "Name of the new dataset" })).toBeVisible();
        await expect(page.getByRole("radio", { name: "Gate camera log" })).toBeVisible();
        await expect(page.getByRole("checkbox")).toHaveCount(3);
        await expect(page.getByText("With no box ticked: Bespoke POLE (the core model)")).toBeVisible();
        await page.getByRole("textbox", { name: "Case name" }).focus();
        await page.keyboard.type("No script");
        await page.getByRole("button", { name: "Create case" }).focus();
        await page.keyboard.press("Enter");
        await expect(page.getByRole("heading", { level: 1 })).toHaveText("No script");
        await expect(page.getByRole("alert")).toContainText("Case made. Its data is loaded in the Ingest Studio");
        await expect(page.getByRole("link", { name: "Open the Ingest Studio" })).toBeVisible();
      },
      "creator",
    );
  });
});
