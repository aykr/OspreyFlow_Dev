// The Ingest Studio's *Analyst promotions* by keyboard alone (ADR-143 decision 10, C9; Amendment 2
// decision 1; rule 13): review a promotion and approve it; reject one with a reason; close its
// details by Escape; merge a removed case's layer through its sheet; cancel that sheet; delete a
// removed case's layer after asking once. No `page.mouse`, no `.click()` in these.
import { expect, test, type Page } from "@playwright/test";

import { PROMOTION_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

async function open(page: Page, query = ""): Promise<void> {
  await page.goto(`/keyboard/promotions-harness.html${query}`);
  await expect(page.getByRole("heading", { name: "Analyst promotions" })).toBeVisible();
}

const sent = (page: Page) => page.evaluate(() => window.__PROMOTIONS__!.sent);

async function press(page: Page, name: string | RegExp): Promise<void> {
  const button = page.getByRole("button", { name, exact: typeof name === "string" });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

test("a promotion is reviewed and approved by keyboard", async ({ page }) => {
  await open(page);
  await press(page, "Review load promotion-wing-1");
  await expect(page.getByRole("heading", { name: /Load promotion-wing-1/ })).toBeFocused();
  await expect(page.getByRole("dialog").getByText("Blue van")).toBeVisible();
  await press(page, "Approve and commit");
  const decided = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/p-1/decision"));
  expect(decided?.body).toEqual({ approve: true });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("status")).toContainText("Approved and committed");
  registerCovered("PROMOTION_ACTIONS", "review-and-approve-a-promotion-by-keyboard");
});

test("a promotion is rejected with a reason by keyboard", async ({ page }) => {
  await open(page);
  await press(page, "Review load promotion-wing-1");
  await expect(page.getByRole("heading", { name: /Load promotion-wing-1/ })).toBeFocused();
  await press(page, "Reject with a reason");
  await press(page, "Reject");
  await expect(page.getByRole("alert")).toContainText("Say why it is rejected");
  const reason = page.getByLabel("Why it is rejected");
  await reason.focus();
  await page.keyboard.type("Source note too thin");
  await press(page, "Reject");
  const decided = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/p-1/decision"));
  expect(decided?.body).toEqual({ approve: false, reason: "Source note too thin" });
  registerCovered("PROMOTION_ACTIONS", "reject-a-promotion-with-a-reason-by-keyboard");
});

test("a promotion's details close on Escape", async ({ page }) => {
  await open(page);
  await press(page, "Review load promotion-wing-1");
  await expect(page.getByRole("heading", { name: /Load promotion-wing-1/ })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect((await sent(page)).some((s) => s.path.endsWith("/decision"))).toBe(false);
  registerCovered("PROMOTION_ACTIONS", "close-a-promotions-details-by-escape");
});

test("one who may not decide is told why, and offered no decision", async ({ page }) => {
  await open(page, "?as=alice");
  await expect(page.getByText("You sent this promotion: a second person must review it.").first()).toBeVisible();
  await press(page, "Details load promotion-wing-1");
  await expect(page.getByRole("button", { name: "Approve and commit" })).toHaveCount(0);
});

test("a removed case's layer is merged through its sheet by keyboard", async ({ page }) => {
  await open(page);
  await press(page, "Merge into the dataset from Old wing");
  const sheet = page.getByRole("dialog", { name: /Merge Old wing's layer into Prison intel/ });
  await expect(page.getByRole("heading", { name: /Merge Old wing's layer/ })).toBeFocused();
  await expect(sheet.getByText(/for this merge alone/)).toBeVisible();
  await expect(page.getByLabel(/Link: seen together/)).toBeDisabled();
  const van = page.getByLabel(/Item: Blue van/);
  await van.focus();
  await page.keyboard.press("Space");
  await expect(van).not.toBeChecked();
  await press(page, "Merge");
  const merged = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/layer-merges/g-1"));
  expect(merged?.body).toEqual({ item_ids: ["i-a"] });
  await expect(page.getByRole("dialog", { name: "Merge sent" })).toContainText("Left out, and why");
  await press(page, "Close");
  // A sent merge closed its own grant (committed or sent for review: one grant, one merge), so
  // nothing is cancelled afterwards.
  expect((await sent(page)).some((s) => s.method === "DELETE" && s.path.endsWith("/layer-merges/g-1"))).toBe(false);
  registerCovered("PROMOTION_ACTIONS", "merge-a-removed-cases-layer-by-keyboard");
});

test("a merge sheet is cancelled by keyboard, its grant closed", async ({ page }) => {
  await open(page);
  await press(page, "Merge into the dataset from Old wing");
  await expect(page.getByRole("heading", { name: /Merge Old wing's layer/ })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: /Merge Old wing's layer/ })).toHaveCount(0);
  await expect.poll(async () => (await sent(page)).some((s) => s.method === "DELETE" && s.path.endsWith("/layer-merges/g-1"))).toBe(true);
  registerCovered("PROMOTION_ACTIONS", "cancel-a-layer-merge-by-keyboard");
});

test("a removed case's layer is deleted after asking once, by keyboard", async ({ page }) => {
  await open(page);
  await press(page, "Delete… Old wing's layer");
  const question = page.getByRole("group", { name: "Delete Old wing's layer?" });
  await expect(question).toBeVisible();
  // Its dry run first, in words; nothing deleted yet.
  await expect(question).toContainText("Nothing has been written");
  expect((await sent(page)).some((s) => s.method === "POST" && s.path.endsWith("/delete/dry-run"))).toBe(true);
  expect((await sent(page)).some((s) => s.method === "DELETE" && s.path.endsWith("/layer"))).toBe(false);
  await press(page, "Delete the layer");
  await expect.poll(async () => (await sent(page)).some((s) => s.method === "DELETE" && s.path.endsWith("/removed-cases/c-old/layer"))).toBe(true);
  await expect(page.getByRole("status")).toContainText("Promoted items were not touched");
  registerCovered("PROMOTION_ACTIONS", "delete-a-removed-cases-layer-after-asking-once-by-keyboard");
});

test("someone who is not one of the dataset's Authors is offered no layer", async ({ page }) => {
  await open(page, "?as=fred");
  await expect(page.getByText(/you are not one of its Authors/).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Removed cases' layers" })).toHaveCount(0);
});

test("every registered promotion action has its own proving test case above", () => {
  assertAllCovered("PROMOTION_ACTIONS", PROMOTION_ACTIONS);
});
