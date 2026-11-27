// The GOV.UK tree's cases page by keyboard alone, with scripts on (slice GR1a; `CLAUDE.md` rule 13; ADR-152 decision 6 and I4; scenario
// CS12). The page is read-only and its only actions are links, so the cases that prove it are the tab order through each page (every
// stop a native one, in the page's own order, the skip link first, the table with no stop of its own) and that each link does what it
// says when activated by Enter: a case's name opens its page, the way back returns to the list, Home is Home. No `page.mouse`, no
// `.click()`. The service is started in the case for the `govuk` tree against a fixture Conduit that refuses what the real routes refuse.
// **New case** (slice GR1b; scenario CS29) is the page's one write: CK4 walks the form's stops, chooses an existing dataset by the
// arrow keys, ticks a box by Space and makes the case by Enter; CK5 makes one with a new dataset, from a refused name to the banner.
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import { buildScratchAssets, tabOrder, viaProxy } from "../helpServer.js";
import type { Assets } from "../helpServer.js";
import { CASE_TAB_ORDER, CREATOR_LIST_TAB_ORDER, LIST_TAB_ORDER, focused, openCases, withCases } from "../casesServer.js";

let assets: Assets;
test.beforeAll(async () => {
  assets = await buildScratchAssets();
});
test.beforeEach(async ({ context }) => {
  await viaProxy(context);
});

test.describe("the cases page with scripts", () => {
  test("CK1: Tab reaches the skip link, the sign-out, each case's link and the way back, in the page's order; the table adds no stop", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Your cases");
      await expect(page.getByRole("table", { name: "Your cases" }).getByRole("row")).toHaveCount(3);
      expect(await tabOrder(page)).toEqual(LIST_TAB_ORDER);
    });
  });

  test("CK2: Enter on a case's name opens its page; its stops come in order; Enter on the way back returns to the list, and Home is Home", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base);
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("main")).toBeFocused();
      await page.getByRole("link", { name: "Harbour watch" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=k-harbour$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Harbour watch");
      await expect(page.getByText("Which vessels berth after dark?")).toBeVisible();
      expect(await tabOrder(page)).toEqual(CASE_TAB_ORDER);
      await page.getByRole("link", { name: "Back to your cases" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/cases$`));
      await page.getByRole("link", { name: "Back to Home" }).focus();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`^${base}/$`));
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Home");
    });
  });

  test("CK3: the landmarks are there, and the cases are a table a reader can move through by its headers", async ({ page }) => {
    await withCases(assets, async (base) => {
      await openCases(page, base);
      await expect(page.getByRole("banner")).toHaveCount(1);
      await expect(page.getByRole("main")).toHaveCount(1);
      const table = page.getByRole("table", { name: "Your cases" });
      await expect(table.getByRole("columnheader")).toHaveText(["Case", "Your level", "Domains", "Datasets", "Made"]);
      await expect(table.getByRole("rowheader")).toHaveText(["Harbour watch", /^Ferry routes\s*You closed this case's tab$/]);
    });
  });
});

const MAKE_NEW = "Make a new dataset — empty, loaded in the Ingest Studio";
const EXISTING = "Use an existing dataset…";

/** Tab to the next stop and check it is the one named: the order is proved a stop at a time. */
async function tabTo(page: Page, name: string): Promise<void> {
  await page.keyboard.press("Tab");
  expect(await focused(page)).toBe(name);
}

test.describe("New case by keyboard", () => {
  test("CK4 (CS29): New case is a stop on the list; the form's stops come in order; the arrow keys choose in both radio groups, Space ticks a box and Enter makes the case", async ({ page }) => {
    await withCases(
      assets,
      async (base) => {
        await openCases(page, base);
        expect(await tabOrder(page)).toEqual(CREATOR_LIST_TAB_ORDER);
        await page.getByRole("link", { name: "New case" }).focus();
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?new=1$`));
        await expect(page.getByRole("heading", { level: 1 })).toHaveText("New case");
        await tabTo(page, "a: Skip to main content");
        await tabTo(page, "button: Sign out");
        await tabTo(page, "input: Case name");
        await page.keyboard.type("Keyboard watch");
        // The data question is one stop, its checked radio; the arrow keys choose within it, and back again.
        await tabTo(page, `input: ${MAKE_NEW}`);
        await page.keyboard.press("ArrowDown");
        expect(await focused(page)).toBe(`input: ${EXISTING}`);
        await expect(page.getByRole("radio", { name: EXISTING })).toBeChecked();
        await page.keyboard.press("ArrowUp");
        await expect(page.getByRole("radio", { name: MAKE_NEW })).toBeChecked();
        await tabTo(page, "input: Name of the new dataset");
        await page.keyboard.press("Shift+Tab");
        await page.keyboard.press("ArrowDown");
        await expect(page.getByRole("radio", { name: EXISTING })).toBeChecked();
        // The datasets are a group of their own: none chosen, then chosen by Space and moved by the arrows.
        await tabTo(page, "input: Gate camera log");
        await page.keyboard.press("Space");
        await expect(page.getByRole("radio", { name: "Gate camera log" })).toBeChecked();
        await page.keyboard.press("ArrowDown");
        await expect(page.getByRole("radio", { name: "Quay ledger" })).toBeChecked();
        await tabTo(page, "input: Financial fraud and AML (FIBO)");
        await page.keyboard.press("Space");
        await expect(page.getByRole("checkbox", { name: "Financial fraud and AML (FIBO)" })).toBeChecked();
        await tabTo(page, "input: Crime case analysis (NIEM)");
        await tabTo(page, "input: Cyber threat analytics (STIX 2.1)");
        await tabTo(page, "button: Create case");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=c-made-1$`));
        await expect(page.getByRole("heading", { level: 1 })).toHaveText("Keyboard watch");
        await expect(page.getByRole("alert")).toContainText("Case made. Its data is loaded in the Ingest Studio");
        await expect(page.getByRole("main")).toContainText("Quay ledger");
        await expect(page.getByRole("main")).toContainText("Financial fraud and AML (FIBO)");
        await expect(page.getByRole("link", { name: "Open the Ingest Studio" })).toHaveCount(0);
      },
      "creator",
    );
  });

  test("CK5 (CS29): a new dataset by keyboard; a refused name is reached from the error summary's link; the banner's link to the Studio is a stop", async ({ page }) => {
    await withCases(
      assets,
      async (base) => {
        await openCases(page, base, "/cases?new=1");
        await page.getByRole("textbox", { name: "Name of the new dataset" }).focus();
        await page.keyboard.type("Quay ledger");
        // Enter in a field sends the form.
        await page.keyboard.press("Enter");
        await expect(page.getByRole("alert")).toContainText("There is a problem");
        await page.getByRole("link", { name: "A dataset with that name may already exist. Choose another name" }).focus();
        await page.keyboard.press("Enter");
        await expect(page.getByRole("textbox", { name: "Name of the new dataset" })).toBeFocused();
        await page.keyboard.press("ControlOrMeta+a");
        await page.keyboard.type("Night berths");
        await page.keyboard.press("Enter");
        await expect(page).toHaveURL(new RegExp(`^${base}/cases\\?case=c-made-1$`));
        await expect(page.getByRole("heading", { level: 1 })).toHaveText("Untitled case");
        await tabTo(page, "a: Skip to main content");
        await tabTo(page, "button: Sign out");
        await tabTo(page, "a: Open the Ingest Studio");
        await tabTo(page, "a: Back to your cases");
      },
      "creator",
    );
  });
});
