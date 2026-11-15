// Case views by keyboard alone (ADR-144; rule 13): a view opened from the saved views list, shared
// with the case, deleted after asking once, opened from another case's row in the cases list, saved
// from its form, and left for the whole case from the strip over an opened saved view. Saving from the canvas
// (the selection bar and a node's menu) is in `keyboard.spec.ts`, asking the model in a view in
// `selection.spec.ts`, and saving a smaller view from the over-cap dialog in `view-over-cap.spec.ts`.
// No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { VIEW_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

async function open(page: Page, query = ""): Promise<void> {
  await page.goto(`/keyboard/views-harness.html${query}`);
  // ADR-145 Amendment 17: the list is *Saved views* (it was *Views in this case*).
  await expect(page.getByRole("list", { name: "Saved views" })).toBeVisible();
}

const state = (page: Page) => page.evaluate(() => window.__VIEWS__!);

async function press(page: Page, name: string): Promise<void> {
  const button = page.getByRole("button", { name, exact: true });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

test("a view is opened from Views in this case by keyboard", async ({ page }) => {
  await open(page);
  await press(page, "Open Payments in March");
  await expect.poll(async () => (await state(page)).opened).toBe("v-shared");
  registerCovered("VIEW_ACTIONS", "open-a-view-from-views-in-this-case-by-keyboard");
});

test("a private view is shared with the case by keyboard, by its creator", async ({ page }) => {
  await open(page);
  await press(page, "Share with the case: Alice's own");
  await expect(page.getByRole("button", { name: "Share with the case: Alice's own" })).toHaveCount(0);
  const sent = (await state(page)).sent;
  expect(sent.some((s) => s.method === "POST" && s.path === "/v1/investigations/c1/views/v-private/share")).toBe(true);
  registerCovered("VIEW_ACTIONS", "share-a-view-with-the-case-by-keyboard");
});

test("a view is deleted by keyboard after asking once, and nothing else is", async ({ page }) => {
  await open(page);
  await press(page, "Delete Alice's own");
  await expect(page.getByText("Delete this view? Nothing on the case is deleted with it.")).toBeVisible();
  expect((await state(page)).sent.some((s) => s.method === "DELETE")).toBe(false);
  await press(page, "Delete view");
  await expect(page.getByRole("button", { name: "Open Alice's own" })).toHaveCount(0);
  const deletes = (await state(page)).sent.filter((s) => s.method === "DELETE");
  expect(deletes).toEqual([{ method: "DELETE", path: "/v1/investigations/c1/views/v-private" }]);
  registerCovered("VIEW_ACTIONS", "delete-a-view-after-asking-once-by-keyboard");
});

test("a view of another case is opened from the cases list by keyboard", async ({ page }) => {
  await open(page);
  await press(page, "Open the view Visits this week of HMP (synthetic demo)");
  await expect.poll(async () => (await state(page)).openedView).toEqual({ caseId: "c2", viewId: "v-hmp" });
  registerCovered("VIEW_ACTIONS", "open-a-view-of-another-case-from-the-cases-list-by-keyboard");
});

test("a view is named and saved from its form by keyboard", async ({ page }) => {
  await open(page, "?show=form");
  const name = page.getByLabel("View name");
  await expect(name).toBeFocused();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("Kestrel's contacts");
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await state(page)).saved).toBe("Kestrel's contacts");
  registerCovered("VIEW_ACTIONS", "save-a-view-from-its-form-by-keyboard");
});

test("Back to the whole case is reached from the strip over an opened saved view by keyboard", async ({ page }) => {
  await open(page, "?show=lens");
  await expect(page.getByRole("region", { name: "Saved view", exact: true })).toContainText("2 items in this view could not be shown");
  await press(page, "Back to the whole case");
  await expect.poll(async () => (await state(page)).back).toBe(true);
  registerCovered("VIEW_ACTIONS", "go-back-to-the-case-from-an-open-view-by-keyboard");
});

// ADR-145 Amendment 17 (the owner, 14 November 2026; ADR-144 Amendment 6 withdrew the graph's *Views ▾*): from the
// case line's *Saved views (n)*, a saved view opened from its panel takes focus to the strip, the case line names it,
// *Back to the whole case* is the strip's first item and the next Tab, and it puts the whole case back and focus on
// *Saved views*; in the dark, light and GOV.UK looks. By keyboard alone (rule 13).
for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  test(`${brand} ${theme}: a saved view opened from the case line takes focus to its strip, and Back to the whole case returns it to Saved views`, async ({ page }) => {
    await page.goto(`/keyboard/views-harness.html?show=way-back${brand === "govuk" ? "&brand=govuk" : ""}`);
    await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
    const caseLine = page.getByRole("region", { name: "You are in the Glass" });
    await expect(page.getByRole("region", { name: "The whole case" })).toHaveText("You are looking at the whole case.");
    await expect(caseLine).not.toContainText("› Saved view:");
    const savedViews = caseLine.getByRole("button", { name: "Saved views (2)", exact: true });
    await savedViews.focus();
    await page.keyboard.press("Enter");
    await expect(savedViews).toHaveAttribute("aria-expanded", "true");
    await press(page, "Open Payments in March");
    const strip = page.getByRole("region", { name: "Saved view", exact: true });
    await expect(strip).toBeFocused();
    await expect(strip).toContainText("Saved view: Payments in March");
    await expect(strip).toContainText("Nothing in a saved view changes the case.");
    await expect(caseLine).toContainText("› Saved view: Payments in March");
    await expect(page.getByRole("region", { name: "The whole case" })).toHaveCount(0);
    // The way back is the strip's first item: the next Tab from the strip.
    await page.keyboard.press("Tab");
    const back = strip.getByRole("button", { name: "Back to the whole case", exact: true });
    await expect(back).toBeFocused();
    if (brand === "govuk") await expect(back).toHaveClass(/govuk-back-link/);
    await page.keyboard.press("Enter");
    await expect(strip).toHaveCount(0);
    await expect(caseLine).not.toContainText("› Saved view:");
    await expect(page.getByRole("region", { name: "The whole case" })).toHaveText("You are looking at the whole case.");
    await expect(savedViews).toBeFocused();
    expect((await state(page)).back).toBe(true);
    registerCovered("VIEW_ACTIONS", "open-a-saved-view-from-the-case-line-and-back-to-the-whole-case-by-keyboard");
  });
}

test("a merged drawing's notes are opened and closed from its view's banner by keyboard", async ({ page }) => {
  await page.goto("/keyboard/views-harness.html?show=merged");
  const toggle = page.getByRole("button", { name: "Notes from the drawing (2)" });
  await toggle.focus();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("Drawn by A. Field, not merged: it stays in the drawing, read-only.")).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Mercer")).toHaveCount(0);
  registerCovered("VIEW_ACTIONS", "open-a-merged-drawings-notes-by-keyboard");
});

test("another member of the case is shown nothing of a private view, and no share or delete", async ({ page }) => {
  await open(page, "?as=bob");
  const panel = page.getByRole("list", { name: "Saved views" });
  // The one view Bob may see, after the whole case's row (ADR-145 Amendment 17).
  await expect(panel.getByRole("listitem")).toHaveCount(2);
  await expect(panel.locator('[data-view-id]:not([data-view-id="whole-case"])')).toHaveCount(1);
  await expect(page.getByText("Alice's own")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Share / })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Delete / })).toHaveCount(0);
  // Tab from the panel's one Open reaches nothing that changes Alice's view.
  await page.getByRole("button", { name: "Open Payments in March" }).focus();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).not.toHaveText(/Share|Delete/);
});

test("every registered case view action has its own proving test case above", () => {
  assertAllCovered("VIEW_ACTIONS", VIEW_ACTIONS);
});

// ADR-145 Amendment 14 decision 1 (the owner, 13 November 2026, on the GOV.UK look: "Open covers the Private
// tag, and the buttons wrap to four lines"): in the real 360 px Cases drawer each view's name and tag share a line
// and its actions fit. Nothing overlaps the tag, the actions are on one line, and all of it is inside the drawer.
// Also with a long view name, and while asking "Delete this view?" (whose question and buttons may wrap, but
// stay inside and off the tag). In each look the scans use, and a row's Open still chosen by keyboard.
for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  for (const state of ["", "&long=1", "&asking=delete"] as const) {
    test(`${brand} ${theme}${state}: in the Cases drawer each view's name, tag and actions fit`, async ({ page }) => {
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(`/keyboard/views-harness.html?in=drawer&brand=${brand}${state}`);
      await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
      const drawer = page.getByRole("dialog", { name: "Cases" });
      await expect(drawer.getByRole("button", { name: /^Open Alice's own/ }).or(drawer.getByRole("button", { name: "Delete view" }))).toBeVisible();
      if (state === "&asking=delete") await expect(drawer.getByRole("button", { name: "Delete view" })).toBeVisible();
      const rows = await page.evaluate(() => {
        const box = (el: Element) => el.getBoundingClientRect();
        const frame = box(document.querySelector("[role='dialog']")!);
        return [...document.querySelectorAll("[data-view-id]")].map((row) => {
          const tag = row.querySelector(".govuk-tag, .view-tag")!;
          const name = row.querySelector(".govuk-summary-list__key, .case-views__name")!;
          const asking = row.querySelector(".case-views__confirm") !== null;
          const actions = [...row.querySelectorAll("button")];
          const overlaps = (a: DOMRect, b: DOMRect) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
          const t = box(tag);
          const n = box(name);
          return {
            id: row.getAttribute("data-view-id"),
            nameBesideTag: t.top < n.bottom && n.top < t.bottom && t.left >= n.right - 0.5,
            tagCovered: actions.some((b) => overlaps(box(b), t)),
            actionLines: asking ? 1 : new Set(actions.map((b) => Math.round(box(b).top))).size,
            outside: [tag, name, ...actions].filter((el) => box(el).right > frame.right + 0.5 || box(el).left < frame.left - 0.5).length,
          };
        });
      });
      // ADR-145 Amendment 17: the list starts with the whole case, its *Open now* tag beside its name and, while it
      // is the one open, no action; each view's row as before.
      expect(rows.map((r) => r.id)).toEqual(["whole-case", "v-private", "v-shared"]);
      for (const row of rows) {
        const actionLines = row.id === "whole-case" ? 0 : 1;
        expect(row, row.id!).toEqual({ id: row.id, nameBesideTag: true, tagCovered: false, actionLines, outside: 0 });
      }
      if (state !== "&asking=delete") {
        await drawer.getByRole("button", { name: /^Open Alice's own/ }).focus();
        await page.keyboard.press("Enter");
        await expect.poll(() => page.evaluate(() => window.__VIEWS__?.opened)).toBe("v-private");
      }
    });
  }
}
