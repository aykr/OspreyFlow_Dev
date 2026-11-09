// The Studio's *1 Model* tab's proposals block by keyboard alone (ADR-143 decision 9; rule 13): a
// proposed link type added to the draft model, and one declined, each with a reason; a decision with
// no reason refused before anything is sent; Escape closing the form and focus going back to the
// button that opened it; the Conduit's refusal of a proposer deciding their own shown in its words.
// No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { MODEL_PROPOSALS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "MODEL_PROPOSALS_ACTIONS";

async function open(page: Page, query = ""): Promise<void> {
  await page.goto(`/keyboard/model-proposals-harness.html${query}`);
  await expect(page.getByRole("heading", { name: "Proposed link types (2 to decide)" })).toBeVisible();
}

const sent = (page: Page) => page.evaluate(() => window.__PROPOSALS__!.sent);

/** Tabs from the top of the page until `name` has focus, as a person would. */
async function tabTo(page: Page, name: string, max = 30): Promise<void> {
  const target = page.getByRole("button", { name, exact: true });
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Tab never reached "${name}"`);
}

test("a proposed type is added to the draft model by keyboard, with a reason", async ({ page }) => {
  await open(page);
  await tabTo(page, "Add Bribed to the draft model…");
  await page.keyboard.press("Enter");
  const why = page.getByLabel("Why? (required)");
  await expect(why).toBeFocused();
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("alert")).toHaveText("Say what stands behind its links: Direct or Probabilistic.");
  expect(await sent(page)).toHaveLength(0);
  // Tab from the reason to the basis, and Space chooses it.
  await page.keyboard.press("Tab");
  await expect(page.getByLabel(/^Direct/)).toBeFocused();
  await page.keyboard.press("Space");
  await expect(page.getByLabel(/^Direct/)).toBeChecked();
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("alert")).toHaveText("Say why: a reason is required.");
  expect(await sent(page)).toHaveLength(0);
  // Shift+Tab from the basis back to the reason.
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByLabel("Why? (required)")).toBeFocused();
  await page.keyboard.type("Seen in three cases this month");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("status")).toHaveText(/Bribed added to the draft model/);
  await expect(page.getByRole("status")).toBeFocused();
  expect(await sent(page)).toEqual([
    { path: "/v1/datasets/ds-1/model/proposals/p1/accept", body: { basis: "direct", reason: "Seen in three cases this month" } },
  ]);
  await expect(page.getByText("In the draft model")).toBeVisible();
  registerCovered(REGISTRY, "add-a-proposed-type-to-the-draft-model-by-keyboard");
});

test("a proposed type is declined by keyboard, Tab reaching the Decline button", async ({ page }) => {
  await open(page);
  await tabTo(page, "Decline Looks out for…");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Why? (required)")).toBeFocused();
  await page.keyboard.type("Use ASSOCIATE_OF");
  await tabTo(page, "Decline");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText(/Looks out for declined/);
  expect((await sent(page))[0]).toEqual({ path: "/v1/datasets/ds-1/model/proposals/p2/decline", body: { reason: "Use ASSOCIATE_OF" } });
  registerCovered(REGISTRY, "decline-a-proposed-type-by-keyboard");
});

test("Escape closes the decision form, sends nothing, and gives focus back to its button", async ({ page }) => {
  await open(page);
  await tabTo(page, "Decline Bribed…");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Why? (required)")).toBeFocused();
  await page.keyboard.type("Not sure");
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Why? (required)")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Decline Bribed…", exact: true })).toBeFocused();
  expect(await sent(page)).toHaveLength(0);
  registerCovered(REGISTRY, "escape-closes-the-decision-form-and-returns-focus");
});

test("the proposer's own is refused in the Conduit's words, by keyboard", async ({ page }) => {
  await open(page, "?as=alice");
  await tabTo(page, "Add Bribed to the draft model…");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Mine, and useful");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Space");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("alert")).toHaveText(
    "You proposed this type, so another data engineer of the dataset decides it.",
  );
  await expect(page.getByText("In the draft model")).toHaveCount(0);
  registerCovered(REGISTRY, "a-refusal-is-shown-in-the-conduits-words-by-keyboard");
});

test("Cancel closes the decision form by keyboard, sends nothing, and gives focus back", async ({ page }) => {
  await open(page);
  await tabTo(page, "Add Bribed to the draft model…");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Not yet");
  await tabTo(page, "Cancel");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Why? (required)")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add Bribed to the draft model…", exact: true })).toBeFocused();
  expect(await sent(page)).toHaveLength(0);
  registerCovered(REGISTRY, "cancel-closes-the-decision-form-by-keyboard");
});

test("an accepted type lost from the model is added again by keyboard", async ({ page }) => {
  await page.goto("/keyboard/model-proposals-harness.html?lost=1");
  await expect(page.getByText("Accepted, not in the model")).toBeVisible();
  await tabTo(page, "Add Bribed to the draft model again…");
  await page.keyboard.press("Enter");
  await page.keyboard.type("Lost with the discarded draft");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Space");
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("status")).toHaveText(/Bribed added to the draft model/);
  expect((await sent(page))[0]).toEqual({
    path: "/v1/datasets/ds-1/model/proposals/p1/accept",
    body: { basis: "direct", reason: "Lost with the discarded draft" },
  });
  registerCovered(REGISTRY, "add-a-lost-type-to-the-draft-model-again-by-keyboard");
});

test("every registered Model tab proposals action has its own proving test case above", () => {
  assertAllCovered("MODEL_PROPOSALS_ACTIONS", MODEL_PROPOSALS_ACTIONS);
});
