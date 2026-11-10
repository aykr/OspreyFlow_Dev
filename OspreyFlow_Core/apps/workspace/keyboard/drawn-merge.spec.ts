// The Ingest Studio's *Merge into a dataset…* by keyboard alone (ADR-143 Amendment 2 decision 6;
// Amendment 3; rule 13): choose the dataset and map and match; tick a match and run the dry run; merge
// what the dry run showed; map a drawn type onto another of the target's types and place its properties
// (Amendment 7); close the merge by Escape. No `page.mouse`, no `.click()` in these.
import { expect, test, type Page } from "@playwright/test";

import { DRAWN_MERGE_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

async function open(page: Page, query = ""): Promise<void> {
  await page.goto(`/keyboard/drawn-merge-harness.html${query}`);
  await expect(page.getByRole("heading", { name: "Merge into a dataset…" })).toBeVisible();
}

const sent = (page: Page) => page.evaluate(() => window.__DRAWN_MERGE__!.sent);

async function press(page: Page, name: string): Promise<void> {
  const button = page.getByRole("button", { name, exact: true });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

async function mapAndMatch(page: Page): Promise<void> {
  const select = page.getByLabel("Merge into");
  await select.focus();
  await expect(select).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(select).toHaveValue("src");
  await press(page, "Map and match");
  await expect(page.getByRole("heading", { name: "Merge Night visits into Prison intel" })).toBeFocused();
}

test("a dataset is chosen and the drawing mapped and matched by keyboard", async ({ page }) => {
  await open(page);
  await mapAndMatch(page);
  await expect(page.getByRole("dialog").getByText(/Vessel is not a type of Prison intel's model\. Map it onto one of its types/)).toBeVisible();
  expect((await sent(page)).some((s) => s.path === "/v1/datasets/d-night/merge-sheet?target=src")).toBe(true);
  registerCovered("DRAWN_MERGE_ACTIONS", "choose-a-dataset-and-map-and-match-a-drawing-by-keyboard");
});

test("a match is ticked and the dry run made by keyboard, and the merge waits for it", async ({ page }) => {
  await open(page);
  await mapAndMatch(page);
  await expect(page.getByRole("button", { name: "4. Merge" })).toBeDisabled();
  const match = page.getByLabel(/Mercer looks like Mercer/);
  await match.focus();
  await page.keyboard.press("Space");
  await expect(match).toBeChecked();
  await press(page, "Dry run");
  await expect(page.getByRole("status")).toContainText("It would add 2 items and 0 links to Prison intel, and propose 1 match");
  await expect(page.getByRole("button", { name: "4. Merge" })).toBeEnabled();
  registerCovered("DRAWN_MERGE_ACTIONS", "tick-a-match-and-run-the-merges-dry-run-by-keyboard");
});

test("the drawing is merged as its dry run showed, by keyboard", async ({ page }) => {
  await open(page);
  await mapAndMatch(page);
  const match = page.getByLabel(/Mercer looks like Mercer/);
  await match.focus();
  await page.keyboard.press("Space");
  await press(page, "Dry run");
  await expect(page.getByRole("status")).toBeVisible();
  await press(page, "4. Merge");
  await expect(page.getByRole("heading", { name: "Merge sent" })).toBeFocused();
  const merge = (await sent(page)).find((s) => s.method === "POST" && s.path === "/v1/datasets/d-night/merges");
  expect(merge?.body).toEqual({
    target_dataset_id: "src",
    item_ids: ["i-1", "i-2", "i-3"],
    matches: [{ drawn: "e-i-1", loaded: "p-loaded" }],
    mapping: [
      { kind: "node", drawn_type: "Person", target_type: "Person", properties: [] },
      { kind: "node", drawn_type: "Vessel", target_type: null, properties: [] },
    ],
  });
  registerCovered("DRAWN_MERGE_ACTIONS", "merge-a-drawn-dataset-after-its-dry-run-by-keyboard");
});

test("a drawn type is mapped onto another of the target's types, its properties placed, by keyboard", async ({ page }) => {
  await open(page);
  await mapAndMatch(page);
  const vessel = page.getByLabel("Vessel goes in as");
  await vessel.focus();
  await expect(vessel).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(vessel).toHaveValue("Organisation");
  await expect(page.getByText(/Each goes in as a new Organisation, a new item beside its drawn one/)).toBeVisible();
  // `name` goes into the Organisation's name; `flag`, not carried until placed, into its country.
  await expect(page.getByLabel("name goes into")).toHaveValue("name");
  const flag = page.getByLabel("flag goes into");
  await flag.focus();
  await expect(flag).toBeFocused();
  for (let n = 0; n < 3; n += 1) await page.keyboard.press("ArrowDown");
  await expect(flag).toHaveValue("country");
  await press(page, "Dry run");
  await expect(page.getByRole("status")).toContainText("It would add 3 items and 0 links to Prison intel, 1 of them as new items of another type");
  await press(page, "4. Merge");
  await expect(page.getByRole("heading", { name: "Merge sent" })).toBeFocused();
  const merge = (await sent(page)).find((s) => s.method === "POST" && s.path === "/v1/datasets/d-night/merges");
  expect((merge?.body as { mapping: unknown }).mapping).toEqual([
    { kind: "node", drawn_type: "Person", target_type: "Person", properties: [] },
    {
      kind: "node",
      drawn_type: "Vessel",
      target_type: "Organisation",
      properties: [
        { drawn_property: "flag", target_property: "country" },
        { drawn_property: "name", target_property: "name" },
      ],
    },
  ]);
  registerCovered("DRAWN_MERGE_ACTIONS", "map-a-drawn-type-onto-another-of-the-targets-types-by-keyboard");
});

test("the merge closes on Escape, nothing sent", async ({ page }) => {
  await open(page);
  await mapAndMatch(page);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect((await sent(page)).some((s) => s.method === "POST")).toBe(false);
  registerCovered("DRAWN_MERGE_ACTIONS", "close-a-drawn-merge-by-escape");
});

test("every registered drawn merge action has its own proving test case above", () => {
  assertAllCovered("DRAWN_MERGE_ACTIONS", DRAWN_MERGE_ACTIONS);
});
