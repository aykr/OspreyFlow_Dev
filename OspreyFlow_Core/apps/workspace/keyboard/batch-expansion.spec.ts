// The batch job's panel by keyboard alone (ADR-151; rule 13), and axe in the three looks for each of
// its states. The panel is `workingset/BatchExpansion.tsx` in `batch-expansion-harness.tsx`, against
// a stand-in of rules-b's route sending its own sentences. It takes focus on its heading when it
// opens; its three actions (*Open the view* on a done job, *Try the batch job again* on a failed one,
// and *Close*) are reached with Tab from there and pressed with Enter. Starting the job from the
// canvas's cap refusal is proved end to end in `canvas-expand-cap.spec.ts`. No `page.mouse`, no `.click()`.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { checkUndecidedContrast } from "../a11y/undecidedContrast";
import { BATCH_EXPANSION_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "BATCH_EXPANSION_ACTIONS";
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function open(page: Page, query: string, look: "dark" | "light" | "govuk" = "dark"): Promise<void> {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/keyboard/batch-expansion-harness.html?${query}${look === "govuk" ? "&brand=govuk" : ""}`);
  if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  if (look === "govuk") await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
  await expect(page.getByRole("heading", { name: "Batch job: the whole expansion" })).toBeFocused();
}

const state = (page: Page) => page.evaluate(() => window.__BATCH__!);
const panel = (page: Page) => page.getByRole("region", { name: "Batch job: the whole expansion" });

/** Tab from where focus is until `name` has it, within the panel's few controls, then Enter. */
async function tabTo(page: Page, name: string): Promise<void> {
  const target = page.getByRole("button", { name, exact: true });
  for (let i = 0; i < 6 && !(await target.evaluate((el) => el === document.activeElement)); i += 1) {
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
  await page.keyboard.press("Enter");
}

test("the panel says each stage in the route's words, and its result is opened as the view by keyboard", async ({ page }) => {
  await open(page, "job=done&step=1");
  const status = panel(page).getByRole("status");
  const to = (stage: number) => page.evaluate((n) => (window.__BATCH__!.stage = n), stage);
  await expect(status).toHaveText("Waiting for the batch expansion to start.");
  for (const [stage, words] of ["Expanding from 12 nodes.", "Counting the links among 41,203 nodes.", "Saving the view."].entries()) {
    await to(stage + 1);
    await expect(status).toHaveText(words);
  }
  await expect(panel(page)).toContainText("Closing this does not stop the job");
  await to(4);
  await expect(status).toHaveText("Saved 41,203 nodes and 96,114 links as your private view “Expansion of Ledger Holdings Ltd”.");
  await expect(panel(page)).not.toContainText("Closing this does not stop the job");
  // Never opened unasked: the reader may be working elsewhere when the job ends.
  await page.waitForTimeout(300);
  expect((await state(page)).opened).toBeNull();
  await tabTo(page, "Open the view");
  await expect.poll(async () => (await state(page)).opened).toBe("v-batch");
  // Its work done, the panel closes; the lens says what is open.
  await expect(panel(page)).toHaveCount(0);
  await expect(page.getByText("The lens shows the view “Expansion of Ledger Holdings Ltd”.")).toBeVisible();
  registerCovered(REGISTRY, "open-a-batch-jobs-view-by-keyboard");
});

test("a failed batch job is tried again by keyboard, and runs to its view", async ({ page }) => {
  await open(page, "job=failed");
  await expect(panel(page).getByRole("alert")).toHaveText(
    "The batch expansion could not finish, and nothing was saved. Try again, or narrow the expansion.",
  );
  await tabTo(page, "Try the batch job again");
  // The button pressed is gone; focus stays in the panel, on its heading, not the page's top.
  await expect(page.getByRole("heading", { name: "Batch job: the whole expansion" })).toBeFocused();
  await expect(page.getByRole("button", { name: "Open the view", exact: true })).toBeVisible();
  expect((await state(page)).sent.filter((s) => s.method === "POST")).toHaveLength(2);
  registerCovered(REGISTRY, "try-a-failed-batch-job-again-by-keyboard");
});

test("the batch job's panel is closed by keyboard while the job runs, and asks no more", async ({ page }) => {
  await open(page, "job=running");
  await expect(panel(page).getByRole("status")).toHaveText("Expanding from 12 nodes.");
  await tabTo(page, "Close");
  await expect.poll(async () => (await state(page)).closed).toBe(true);
  await expect(panel(page)).toHaveCount(0);
  const asked = (await state(page)).sent.length;
  await page.waitForTimeout(600);
  expect((await state(page)).sent.length).toBe(asked);
  registerCovered(REGISTRY, "close-the-batch-job-panel-by-keyboard");
});

test("a job already running in the case is followed, not refused", async ({ page }) => {
  await open(page, "job=following");
  await expect(panel(page).getByRole("status")).toHaveText("Expanding from 12 nodes.");
  await expect(panel(page).getByRole("alert")).toHaveCount(0);
  const reads = (await state(page)).sent.filter((s) => s.method === "GET");
  expect(reads.length).toBeGreaterThan(0);
  expect(reads.every((s) => s.path.endsWith("/batch-expansions/j-running"))).toBe(true);
});

// Each state the panel draws, in each of the three looks, with no automated WCAG 2.2 A or AA violation.
const STATES: [string, (page: Page) => Promise<void>][] = [
  ["running", (page) => expect(panel(page).getByRole("status")).toHaveText("Expanding from 12 nodes.")],
  ["done", (page) => expect(page.getByRole("button", { name: "Open the view", exact: true })).toBeVisible()],
  ["refused", (page) => expect(panel(page).getByRole("alert")).toContainText("812,000 nodes against a limit of 500,000")],
  ["failed", (page) => expect(page.getByRole("button", { name: "Try the batch job again" })).toBeVisible()],
  ["forbidden", (page) => expect(panel(page).getByRole("alert")).toHaveText("You hold Reader in this case; this needs Editor.")],
  ["noright", (page) => expect(panel(page).getByRole("alert")).toContainText("does not hold the right to expand")],
  ["overlimit", async (page) => {
    await tabTo(page, "Open the view");
    await expect(panel(page).getByRole("alert")).toContainText("Nothing was cut to fit");
  }],
  ["trouble", (page) => expect(panel(page)).toContainText("Still trying.")],
  ["following", (page) => expect(panel(page).getByRole("status")).toHaveText("Expanding from 12 nodes.")],
  ["deleted", (page) => expect(panel(page).getByRole("alert")).toHaveText("The batch expansion finished, but the view it saved has since been deleted.")],
];
for (const look of ["dark", "light", "govuk"] as const) {
  for (const [job, drawn] of STATES) {
    test(`the batch job's panel, ${job}, has no automated WCAG 2.2 A or AA violation (${look})`, async ({ page }) => {
      await open(page, `job=${job}`, look);
      await drawn(page);
      const results = await new AxeBuilder({ page }).include(".batch-expansion").withTags(WCAG_TAGS).analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      const contrast = await checkUndecidedContrast(page, results);
      expect(contrast.unlisted, "colour contrast axe left undecided").toEqual([]);
    });
  }
}

test("every registered batch job action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, BATCH_EXPANSION_ACTIONS);
});
