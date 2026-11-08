// A keyboard-only walkthrough of the view-over-the-cap dialog (ADR-124 decision 2, `CLAUDE.md` rule 13):
// it appears when the server says the reader's view is past a cap; "Try again" sends the resync with no
// last sequence; "Save as a view" can choose a type and submit, and the filtered view is saved and
// opened (`save_as_view`, ADR-144); Escape puts it away.
import { expect, test } from "@playwright/test";

import { VIEW_OVER_CAP_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const OVER_CAP = {
  seq: 5,
  op: "view_over_cap",
  would_be: {
    error: "limit_exceeded",
    cap_kind: "nodes",
    cap: 50_000,
    would_be: 50_001,
    options: ["save_as_view", "filter", "promote_to_batch"],
  },
};

test("the dialog appears on a view_over_cap; Try again resyncs from nothing; a smaller view can be saved and opened by keyboard", async ({ page }) => {
  const saves: { url: string; body: unknown }[] = [];
  const view = { id: "v1", case_id: "c1", name: "Smaller view of this case", created_by: "k", created_at: "2026-11-08T10:00:00Z", shared: false, chosen: null };
  await page.route("**/*/v1/investigations/c1/views", async (route) => {
    saves.push({ url: route.request().url(), body: route.request().postDataJSON() });
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(view) });
  });
  await page.route("**/*/v1/investigations/c1/views/v1", async (route) => {
    const node = { id: "n1", type: "Person" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ view, nodes: [node], edges: [], layout: {}, missing: 0 }) });
  });
  await page.goto("/keyboard/view-over-cap-harness.html");
  await expect(page.getByText("The view is within the limit.")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  // A snapshot first, so that the client holds a last sequence for "Try again" to leave out.
  await page.evaluate(() => window.__OVERCAP__!.deliver({ seq: 4, op: "snapshot", nodes: [], edges: [] }));
  await page.evaluate((message) => window.__OVERCAP__!.deliver(message), OVER_CAP);
  const dialog = page.getByRole("dialog", { name: "Your view of this case is too large" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Too many for the canvas: 50,001 nodes against a limit of 50,000.");
  expect(await page.evaluate(() => document.querySelector('[role="dialog"]')!.contains(document.activeElement))).toBe(true);
  registerCovered("VIEW_OVER_CAP_ACTIONS", "see-the-over-cap-dialog-when-the-server-says-the-view-is-too-large");

  // Try again: the first control is "Save as a view", the second "Try again".
  const sentBefore = await page.evaluate(() => window.__OVERCAP__!.sent.length);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Try again" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__OVERCAP__!.sent.length)).toBe(sentBefore + 1);
  expect(await page.evaluate(() => window.__OVERCAP__!.sent.at(-1))).toBe(JSON.stringify({ last_acknowledged_seq: null }));
  registerCovered("VIEW_OVER_CAP_ACTIONS", "try-again-from-the-over-cap-dialog-by-keyboard");

  // Save as a view: Enter on the action, Space on a type, Enter on the submit.
  await page.getByRole("button", { name: "Save as a view" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Entity types" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Person" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("checkbox", { name: "Person" })).toBeChecked();
  await page.getByRole("button", { name: "Save and open the view" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => saves.length).toBe(1);
  expect(saves[0].body).toEqual({ name: "Smaller view of this case", filter: { entity_types: ["Person"] } });
  await expect.poll(() => page.evaluate(() => window.__OVERCAP__!.opened)).toEqual(["v1"]);
  // The view is open as the lens: with no snapshot (the case is still past the cap), the dialog is
  // gone and holds no focus, so the view can be worked by keyboard.
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const back = page.getByRole("button", { name: "Back to the case" });
  await back.focus();
  await expect(back).toBeFocused();
  registerCovered("VIEW_OVER_CAP_ACTIONS", "choose-a-type-and-save-a-view-by-keyboard");

  // Back to the case, which is still past the cap: the dialog shows again.
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Your view of this case is too large" })).toBeVisible();

  // A snapshot (the answer to trying again) takes the dialog away.
  await page.evaluate(() => window.__OVERCAP__!.deliver({ seq: 6, op: "snapshot", nodes: [], edges: [] }));
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("Escape puts the dialog away, and a button brings it back", async ({ page }) => {
  await page.goto("/keyboard/view-over-cap-harness.html");
  await expect(page.getByText("The view is within the limit.")).toBeVisible();
  await page.evaluate((message) => window.__OVERCAP__!.deliver(message), OVER_CAP);
  await expect(page.getByRole("dialog")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  // Focus goes to the button that brings it back, so Enter alone does.
  await expect(page.getByRole("button", { name: /Choose what to do/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  registerCovered("VIEW_OVER_CAP_ACTIONS", "put-the-over-cap-dialog-away-with-escape-by-keyboard");
});

test("every registered over-cap dialog action has its own proving test case above", () => {
  assertAllCovered("VIEW_OVER_CAP_ACTIONS", VIEW_OVER_CAP_ACTIONS);
});
