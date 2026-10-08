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

test("who shares contacts with a node is asked, and a pair put on the canvas, by keyboard", async ({ page }) => {
  await page.route("**/*/v1/investigations/inv-1/nodes/a/shared-contacts**", async (route) => {
    const post = route.request().method() === "POST";
    const body = post
      ? { delta: { op: "add", seq: 5, nodes: [], edges: [] }, added_nodes: 3, added_links: 4 }
      : {
          contacts: [{ node: { id: "b", type: "Person", properties: { family_name: "Skilling" }, provenance: { state: "asserted", sources: [], first_seen: "2026-01-01T00:00:00Z" }, handling: { classification: "OFFICIAL", handling_code: "P", originator: "unit-1", owning_unit: "unit-1" }, audit: { created_at: "2026-01-01T00:00:00Z", created_by: "fixture" } }, shared: 7 }],
          total: 1,
        };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/keyboard/inspector-harness.html?view=node");
  const header = page.getByRole("button", { name: "Shares contacts" });
  await header.focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Who shares two contacts by “Associate of”?" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Skilling · shares 7" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__INSPECTOR__?.deltas)).toEqual([5]);
  await expect(page.getByText("3 nodes and 4 links added.")).toBeVisible();
  registerCovered(REGISTRY, "ask-who-shares-contacts-and-add-a-pair-by-keyboard");
});

test("every registered Inspector action has its own proving test case above", () => {
  assertAllCovered("INSPECTOR_ACTIONS", INSPECTOR_ACTIONS);
});
