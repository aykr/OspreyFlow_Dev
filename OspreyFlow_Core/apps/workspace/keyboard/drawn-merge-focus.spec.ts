// GG1 (WCAG 3.2.2; rule 13): the drawn-merge sheet moves focus onto its heading only when it is first
// drawn and when the merge is sent. Changing a "goes in as" or "goes into" select reads Match again;
// that read must leave focus on the select, and a Match box toggled afterwards keeps it too. No
// `page.mouse`, no `.click()` in these.
import { expect, test, type Page } from "@playwright/test";

const HEADING = "Merge Night visits into Prison intel";

async function open(page: Page): Promise<void> {
  await page.goto("/keyboard/drawn-merge-harness.html");
  await expect(page.getByRole("heading", { name: "Merge into a dataset…" })).toBeVisible();
}

const sent = (page: Page) => page.evaluate(() => window.__DRAWN_MERGE__!.sent);

async function press(page: Page, name: string): Promise<void> {
  const button = page.getByRole("button", { name, exact: true });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

/** Matches read again under a chosen mapping: the request is made (`mapping=` on the sheet read), and
 * its answer then drawn, which is when a stray focus move would land. */
async function matchesReadAgain(page: Page, times: number): Promise<void> {
  await expect
    .poll(async () => (await sent(page)).filter((s) => s.path.startsWith("/v1/datasets/d-night/merge-sheet?") && s.path.includes("mapping=")).length)
    .toBe(times);
  // Let the answer arrive and the sheet draw it (and any effect on it run).
  await page.evaluate(
    () => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(done, 100))))),
  );
}

async function mapAndMatch(page: Page): Promise<void> {
  const select = page.getByLabel("Merge into", { exact: true });
  await select.focus();
  await select.selectOption("src");
  await press(page, "Map and match");
  // First drawn: the heading takes focus.
  await expect(page.getByRole("heading", { name: HEADING })).toBeFocused();
}

test("changing a 'goes in as' or 'goes into' select leaves focus on that select", async ({ page }) => {
  await open(page);
  await mapAndMatch(page);

  const vessel = page.getByLabel("Vessel goes in as");
  await vessel.focus();
  await expect(vessel).toBeFocused();
  await vessel.selectOption("Organisation");
  await matchesReadAgain(page, 1);
  await expect(page.getByText(/Each goes in as a new Organisation/)).toBeVisible();
  await expect(vessel).toBeFocused();

  const flag = page.getByLabel("flag goes into");
  await flag.focus();
  await expect(flag).toBeFocused();
  await flag.selectOption("country");
  await matchesReadAgain(page, 2);
  await expect(flag).toBeFocused();
  await expect(page.getByRole("heading", { name: HEADING })).not.toBeFocused();
});

test("a Match box toggled after a mapping choice keeps focus", async ({ page }) => {
  await open(page);
  await mapAndMatch(page);
  const vessel = page.getByLabel("Vessel goes in as");
  await vessel.focus();
  await vessel.selectOption("Organisation");
  await matchesReadAgain(page, 1);

  const match = page.getByLabel(/Mercer looks like Mercer/);
  await match.focus();
  await expect(match).toBeFocused();
  await page.keyboard.press("Space");
  await expect(match).toBeChecked();
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(done, 100)))));
  await expect(match).toBeFocused();
  await page.keyboard.press("Space");
  await expect(match).not.toBeChecked();
  await expect(match).toBeFocused();
});

test("the heading takes focus again when the merge is sent", async ({ page }) => {
  await open(page);
  await mapAndMatch(page);
  const vessel = page.getByLabel("Vessel goes in as");
  await vessel.focus();
  await vessel.selectOption("Organisation");
  await matchesReadAgain(page, 1);
  await expect(vessel).toBeFocused();
  await press(page, "Dry run");
  await expect(page.getByRole("status")).toBeVisible();
  await press(page, "4. Merge");
  await expect(page.getByRole("heading", { name: "Merge sent" })).toBeFocused();
});
