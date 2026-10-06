// The Inspector's parts by keyboard alone (ADR-096, rule 13): a part opens and folds by Enter on
// its header; opening *Change this link* lands in the form; a link-menu hand-over opens its part.
// No `page.mouse`, no `.click()`. The link's notes, events and history are answered at the
// transport, empty, as the server answers a link with none.
import { expect, test, type Page } from "@playwright/test";

import { INSPECTOR_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "INSPECTOR_ACTIONS";

async function serve(page: Page) {
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/v1/investigations/inv-1/links/e1/notes", (r) => r.fulfill(json({ notes: [] })));
  await page.route("**/v1/investigations/inv-1/links/e1/history", (r) => r.fulfill(json({ changes: [], truncated: false })));
  await page.route("**/v1/investigations/inv-1/links/e1/events**", (r) =>
    r.fulfill(json({ total: 0, offset: 0, limit: 50, events: [] })),
  );
}

const header = (page: Page, name: string) => page.getByRole("button", { name, exact: true });

test("a part opens and folds by Enter on its header", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/inspector-harness.html");
  await expect(header(page, "Details")).toHaveAttribute("aria-expanded", "true");
  await header(page, "Notes").focus();
  await expect(header(page, "Notes")).toHaveAttribute("aria-expanded", "false");
  await page.keyboard.press("Enter");
  await expect(header(page, "Notes")).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("region", { name: "Notes" })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Notes" })).toHaveCount(0);
  registerCovered(REGISTRY, "a-part-opens-and-folds-by-keyboard");
});

test("opening Change this link by keyboard lands in the form, at the link type", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/inspector-harness.html");
  await header(page, "Change this link").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Link type")).toBeFocused();
  registerCovered(REGISTRY, "opening-change-this-link-opens-the-form");
});

test("a link-menu hand-over opens its part", async ({ page }) => {
  await serve(page);
  await page.goto("/keyboard/inspector-harness.html");
  await expect(header(page, "Notes")).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("button", { name: "Hand over: Add a note" }).focus();
  await page.keyboard.press("Enter");
  await expect(header(page, "Notes")).toHaveAttribute("aria-expanded", "true");
  registerCovered(REGISTRY, "a-menu-hand-over-opens-its-part");
});

test("every registered Inspector action has its own proving test case above", () => {
  assertAllCovered("INSPECTOR_ACTIONS", INSPECTOR_ACTIONS);
});
