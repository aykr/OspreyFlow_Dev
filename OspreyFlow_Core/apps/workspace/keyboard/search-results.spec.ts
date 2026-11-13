// The search results page by keyboard alone (the owner's navigation decision of 13 November 2026, Part A; ADR-145
// Amendment 15 Part A; rule 13), on `search-results-harness.html`: the real search box and results page, wired as
// `App.tsx` wires them. Enter on the typed words opens the results with focus on their heading; a group, a filter and
// the next page are chosen; a result is shown on the graph and a document opened; the Ask line hands the words over;
// Back returns to the view with focus in the search box. In dark, light and GOV.UK. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { SEARCH_RESULTS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "SEARCH_RESULTS_ACTIONS";
const state = (page: Page) => page.evaluate(() => window.__SEARCH__!);
const heading = (page: Page) => page.getByRole("heading", { name: "Search results for 'Kestrel'" });

async function press(page: Page, name: string | RegExp): Promise<void> {
  const button = page.getByRole("button", { name, exact: typeof name === "string" });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

async function openByEnter(page: Page, query: string): Promise<void> {
  await page.goto(`/keyboard/search-results-harness.html${query}`);
  const box = page.getByRole("combobox", { name: "Search entities, identifiers, documents" });
  await box.focus();
  await page.keyboard.type("Kestrel");
  await page.keyboard.press("Enter");
  await expect(heading(page)).toBeFocused();
}

for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  const query = brand === "govuk" ? "?brand=govuk" : "";
  const look = async (page: Page) => page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);

  test(`${brand} ${theme}: Enter in the search box opens the results, focus on their heading, the view left out of reach`, async ({ page }) => {
    await openByEnter(page, query);
    await look(page);
    await expect(page.getByText("57 records", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "A control on the graph" })).not.toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.getByRole("button", { name: "Back to Graph" })).toBeFocused();
    // Nothing of the view beneath is in the Tab order while the results show.
    for (let i = 0; i < 30; i++) {
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: "A control on the graph" })).not.toBeFocused();
    }
    expect((await state(page)).sent).toHaveLength(1);
    registerCovered(REGISTRY, "open-search-results-by-keyboard");
  });

  test(`${brand} ${theme}: a group, a dataset and the next page are chosen by keyboard`, async ({ page }) => {
    await openByEnter(page, query);
    await look(page);
    await press(page, /^People/);
    await expect(page.getByRole("button", { name: /^People/ })).toHaveAttribute("aria-pressed", "true");
    await expect.poll(async () => (await state(page)).sent.at(-1)).toMatchObject({ group: "Person", page: 1 });
    registerCovered(REGISTRY, "choose-a-result-group-by-keyboard");
    const dataset = page.getByRole("checkbox", { name: "Fixture Corp (40)" });
    await dataset.focus();
    await page.keyboard.press("Space");
    await expect(dataset).toBeChecked();
    await expect.poll(async () => (await state(page)).sent.at(-1)).toMatchObject({ filters: { datasets: ["ds-1"] } });
    registerCovered(REGISTRY, "filter-search-results-by-keyboard");
    await press(page, "Next page");
    await expect.poll(async () => (await state(page)).sent.at(-1)).toMatchObject({ page: 2 });
    await expect(page.getByRole("button", { name: "Previous page" })).toBeVisible();
    registerCovered(REGISTRY, "next-page-of-results-by-keyboard");
  });

  test(`${brand} ${theme}: a result is shown on the graph, a document opened and the Ask line followed, by keyboard`, async ({ page }) => {
    await openByEnter(page, query);
    await look(page);
    const name = await page.getByRole("list", { name: "Results" }).getByRole("heading", { level: 3 }).last().textContent();
    await press(page, `Open ${name}`);
    await expect.poll(async () => (await state(page)).opened).toEqual(["d1"]);
    registerCovered(REGISTRY, "open-a-document-from-the-results-by-keyboard");
    await press(page, "Ask a question about 'Kestrel' instead");
    await expect.poll(async () => (await state(page)).asked).toEqual(["Kestrel"]);
    registerCovered(REGISTRY, "ask-instead-from-the-results-by-keyboard");
    const first = await page.getByRole("list", { name: "Results" }).getByRole("heading", { level: 3 }).first().textContent();
    await press(page, `Show on graph: ${first}`);
    await expect.poll(async () => (await state(page)).shown).toEqual([["p1"]]);
    await expect(heading(page)).toHaveCount(0);
    registerCovered(REGISTRY, "show-a-result-on-the-graph-by-keyboard");
  });

  test(`${brand} ${theme}: Back returns to the view, focus in the search box`, async ({ page }) => {
    await openByEnter(page, query);
    await look(page);
    await press(page, "Back to Graph");
    await expect(heading(page)).toHaveCount(0);
    await expect(page.getByRole("combobox", { name: "Search entities, identifiers, documents" })).toBeFocused();
    // The view is back in reach: Tab arrives at its control within a few steps.
    const control = page.getByRole("button", { name: "A control on the graph" });
    for (let i = 0; i < 6 && !(await control.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
    await expect(control).toBeFocused();
    registerCovered(REGISTRY, "back-from-the-results-by-keyboard");
  });
}

test("a suggestion moved to with the arrow keys is chosen by Enter, and no results page opens", async ({ page }) => {
  await page.goto("/keyboard/search-results-harness.html");
  const box = page.getByRole("combobox", { name: "Search entities, identifiers, documents" });
  await box.focus();
  await page.keyboard.type("Kestrel");
  await expect(page.getByRole("option").first()).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(heading(page)).toHaveCount(0);
  expect((await state(page)).sent).toHaveLength(0);
});

// Last in the file: the check reads the cases above it, run in order on one worker (CI's two-core runner).
test("every registered search results action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, SEARCH_RESULTS_ACTIONS);
});
