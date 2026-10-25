// A keyboard-only walkthrough of the view-over-the-cap dialog (ADR-124 decision 2, `CLAUDE.md` rule 13):
// it appears when the server says the reader's view is past a cap; "Try again" sends the resync with no
// last sequence; "Open a filtered branch" can choose a type and submit, and the request is sent; Escape
// puts it away.
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
    options: ["branch", "filter", "promote_to_batch"],
  },
};

test("the dialog appears on a view_over_cap; Try again resyncs from nothing; a branch can be opened by keyboard", async ({ page }) => {
  const branchRequests: { url: string; body: unknown }[] = [];
  await page.route("**/*/v1/investigations/c1/branch-by-filter", async (route) => {
    branchRequests.push({ url: route.request().url(), body: route.request().postDataJSON() });
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "b1", name: "Branch of Case" }) });
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

  // Try again: the first control is "Open a filtered branch", the second "Try again".
  const sentBefore = await page.evaluate(() => window.__OVERCAP__!.sent.length);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Try again" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__OVERCAP__!.sent.length)).toBe(sentBefore + 1);
  expect(await page.evaluate(() => window.__OVERCAP__!.sent.at(-1))).toBe(JSON.stringify({ last_acknowledged_seq: null }));
  registerCovered("VIEW_OVER_CAP_ACTIONS", "try-again-from-the-over-cap-dialog-by-keyboard");

  // Open a filtered branch: Enter on the action, Space on a type, Enter on the submit.
  await page.getByRole("button", { name: "Open a filtered branch" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Entity types" })).toBeVisible();
  await page.getByRole("checkbox", { name: "Person" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("checkbox", { name: "Person" })).toBeChecked();
  await page.getByRole("button", { name: "Open branch" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => branchRequests.length).toBe(1);
  expect(branchRequests[0].body).toEqual({ entity_types: ["Person"] });
  expect(branchRequests[0].url).toContain("/v1/investigations/c1/branch-by-filter");
  await expect.poll(() => page.evaluate(() => window.__OVERCAP__!.opened)).toEqual(["b1"]);
  registerCovered("VIEW_OVER_CAP_ACTIONS", "choose-a-type-and-open-a-filtered-branch-by-keyboard");

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
