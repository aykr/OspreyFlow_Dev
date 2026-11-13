// Case views by keyboard alone (ADR-144; rule 13): a view opened from *Views in this case*, shared
// with the case, deleted after asking once, opened from another case's row in the cases list, saved
// from its form, and left for the case from the banner over an opened view. Saving from the canvas
// (the selection bar and a node's menu) is in `keyboard.spec.ts`, asking the model in a view in
// `selection.spec.ts`, and saving a smaller view from the over-cap dialog in `view-over-cap.spec.ts`.
// No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { VIEW_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

async function open(page: Page, query = ""): Promise<void> {
  await page.goto(`/keyboard/views-harness.html${query}`);
  await expect(page.getByRole("list", { name: "Views in this case" })).toBeVisible();
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

test("Back to the case is reached from the banner over an opened view by keyboard", async ({ page }) => {
  await open(page, "?show=lens");
  await expect(page.getByRole("region", { name: "Open view" })).toContainText("2 items in this view could not be shown");
  await press(page, "Back to the case");
  await expect.poll(async () => (await state(page)).back).toBe(true);
  registerCovered("VIEW_ACTIONS", "go-back-to-the-case-from-an-open-view-by-keyboard");
});

// ADR-144 Amendment 3 (the owner, 13 November 2026): the graph's *Views ▾*, opened, a view chosen, the lens
// open on it, and *Back to the case*, each by keyboard alone.
test("a view is opened from Views by the graph by keyboard, and Back to the case closes it", async ({ page }) => {
  await open(page, "?show=menu");
  const views = page.getByRole("toolbar", { name: "Canvas tools" }).getByRole("button", { name: "Views" });
  await views.focus();
  await page.keyboard.press("Enter");
  const menu = page.getByRole("group", { name: "Saved views in this case" });
  await expect(menu.getByRole("button")).toHaveText(["Alice's ownPrivate", "Payments in MarchShared"]);
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  await expect(menu.getByRole("button", { name: /^Payments in March/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(async () => (await state(page)).opened).toBe("v-shared");
  await expect(menu).toHaveCount(0);
  const lens = page.getByRole("region", { name: "Open view" });
  await expect(lens).toContainText("Payments in March");
  // The open view is marked in the menu when it is opened again.
  await views.focus();
  await page.keyboard.press("Enter");
  await expect(menu.getByRole("button", { name: /^Payments in March/ })).toHaveAttribute("aria-current", "true");
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(views).toBeFocused();
  await press(page, "Back to the case");
  await expect(lens).toHaveCount(0);
  await expect.poll(async () => (await state(page)).back).toBe(true);
  registerCovered("VIEW_ACTIONS", "open-a-view-from-views-by-the-graph-by-keyboard");
});

test("Views by the graph says how to make one when the case has none, by keyboard", async ({ page }) => {
  await page.goto("/keyboard/views-harness.html?show=menu&empty=1");
  const views = page.getByRole("toolbar", { name: "Canvas tools" }).getByRole("button", { name: "Views" });
  await views.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Saved views in this case" })).toHaveText(
    "No saved views yet. Select nodes and choose Save as a view.",
  );
});

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
  const panel = page.getByRole("list", { name: "Views in this case" });
  await expect(panel.getByRole("listitem")).toHaveCount(1);
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
// tag, and the buttons wrap to four lines"): in the real 360 px Cases drawer each view's name, its tag and its
// actions fit. Nothing overlaps, the actions are on one line, and all of it is inside the drawer. In each look
// the scans use, and each action still chosen by keyboard.
for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  test(`${brand} ${theme}: in the Cases drawer each view's name, tag and actions fit`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/views-harness.html?in=drawer&brand=${brand}`);
    await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
    const drawer = page.getByRole("dialog", { name: "Cases" });
    await expect(drawer.getByRole("button", { name: "Open Alice's own" })).toBeVisible();
    const rows = await page.evaluate(() => {
      const box = (el: Element) => el.getBoundingClientRect();
      const frame = box(document.querySelector("[role='dialog']")!);
      return [...document.querySelectorAll("[data-view-id]")].map((row) => {
        const tag = row.querySelector(".govuk-tag, .view-tag")!;
        const actions = [...row.querySelectorAll("button")];
        const overlaps = (a: DOMRect, b: DOMRect) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
        const t = box(tag);
        return {
          id: row.getAttribute("data-view-id"),
          tagCovered: actions.some((b) => overlaps(box(b), t)),
          actionLines: new Set(actions.map((b) => Math.round(box(b).top))).size,
          outside: [tag, ...actions].filter((el) => box(el).right > frame.right + 0.5 || box(el).left < frame.left - 0.5).length,
        };
      });
    });
    expect(rows.map((r) => r.id)).toEqual(["v-private", "v-shared"]);
    for (const row of rows) expect(row, row.id!).toEqual({ id: row.id, tagCovered: false, actionLines: 1, outside: 0 });
    await drawer.getByRole("button", { name: "Open Alice's own" }).focus();
    await page.keyboard.press("Enter");
    await expect.poll(() => page.evaluate(() => window.__VIEWS__?.opened)).toBe("v-private");
  });
}
