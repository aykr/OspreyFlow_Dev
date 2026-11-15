// The search results page by keyboard alone (the owner's navigation decision of 13 November 2026, Part A; ADR-145
// Amendment 15 Part A; rule 13), on `search-results-harness.html`: the real search box and results page, through the
// App's own `useSearchResultsOverlay`. Enter on the typed words opens the results with focus on their heading; a group,
// a dataset, the next and previous page and the dates are chosen and the filters cleared; a result is shown on the
// graph and a document read and closed; the Ask line hands the words over; Back returns to the view with focus in the
// search box. In dark, light and GOV.UK. No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { SEARCH_RESULTS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "SEARCH_RESULTS_ACTIONS";
const state = (page: Page) => page.evaluate(() => window.__SEARCH__!);
const heading = (page: Page) => page.getByRole("heading", { name: "Search results for 'Kestrel'" });

async function press(page: Page, name: string | RegExp): Promise<void> {
  // GOV.UK's pagination is links; everything else here is a button.
  const exact = typeof name === "string";
  const button = page.getByRole("button", { name, exact }).or(page.getByRole("link", { name, exact }));
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
    // The new page's top: focus on the heading, never lost with the button that was pressed.
    await expect(heading(page)).toBeFocused();
    registerCovered(REGISTRY, "next-page-of-results-by-keyboard");
    await press(page, "Previous page");
    await expect.poll(async () => (await state(page)).sent.at(-1)).toMatchObject({ page: 1 });
    await expect(heading(page)).toBeFocused();
    registerCovered(REGISTRY, "previous-page-of-results-by-keyboard");
    await press(page, "Clear filters");
    // Exactly no filter: toMatchObject's {} would match any filters at all.
    await expect.poll(async () => ((await state(page)).sent.at(-1) as { filters: unknown }).filters).toEqual({});
    await expect(dataset).not.toBeChecked();
    await expect(heading(page)).toBeFocused();
    registerCovered(REGISTRY, "clear-search-filters-by-keyboard");
  });

  test(`${brand} ${theme}: the results are filtered by date by keyboard`, async ({ page }) => {
    await openByEnter(page, query);
    await look(page);
    if (brand === "govuk") {
      // GOV.UK's date input: a day, a month and a year, each typed.
      const from = page.getByRole("group", { name: "From" });
      for (const [label, text] of [["Day", "1"], ["Month", "2"], ["Year", "2026"]] as const) {
        await from.getByLabel(label).focus();
        await page.keyboard.type(text);
      }
    } else {
      const from = page.getByLabel("From", { exact: true });
      await from.focus();
      await from.fill("2026-02-01");
    }
    await expect.poll(async () => (await state(page)).sent.at(-1)).toMatchObject({ filters: { date_from: "2026-02-01" } });
    registerCovered(REGISTRY, "filter-results-by-date-by-keyboard");
  });

  test(`${brand} ${theme}: a result is shown on the graph, a document opened and the Ask line followed, by keyboard`, async ({ page }) => {
    await openByEnter(page, query);
    await look(page);
    const name = await page.getByRole("list", { name: "Results" }).getByRole("heading", { level: 3 }).last().textContent();
    await press(page, `Open ${name}`);
    await expect.poll(async () => (await state(page)).opened).toEqual(["d1"]);
    // Read over the view, the results hidden (drawn hidden, not only marked so), and back in them when it closes.
    await expect(page.locator("section.search-results")).toBeHidden();
    await press(page, "Close");
    await expect(heading(page)).toBeVisible();
    await expect(heading(page)).toBeFocused();
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

test("a pasted query longer than the search takes is kept whole in the box, and the refusal names the limit (rule 2)", async ({ page }) => {
  await page.goto("/keyboard/search-results-harness.html");
  const box = page.getByRole("combobox", { name: "Search entities, identifiers, documents" });
  await box.focus();
  const long = "Kestrel ".repeat(26).trim(); // 207 characters
  await page.keyboard.insertText(long);
  await expect(box).toHaveValue(long);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("alert")).toContainText(
    "The search could not be done: a search can be at most 200 characters, and this one has 207. Shorten it and press Enter again.",
  );
  expect((await state(page)).sent.map((b) => (b as { query: string }).query)).toEqual([long]);
});

// Last in the file: the check reads the cases above it, run in order on one worker (CI's two-core runner).
// Found on the live demo at the candidate 574a05c, 15 November 2026 (GOV.UK look, 1440 by 900): the results page was
// drawn under the Graph's own toolbar and zoom column, its heading covered. The results fill the main area over the
// view left (Part A), so nothing of that view may be drawn over them: at points across the whole page, and at the
// canvas toolbar's and the zoom column's own centres, what is drawn is the results page; in each look.
for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  test(`${brand} ${theme}: the results page is drawn over the whole of the view it covers, the canvas's toolbar and zoom column included`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/search-results-harness.html?canvas=1&open=1${brand === "govuk" ? "&brand=govuk" : ""}`);
    await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
    await expect(page.getByRole("heading", { name: "Search results for 'Kestrel'" })).toBeVisible();
    // The canvas is really there beneath, toolbar and zoom column drawn, so the case can fail.
    await expect(page.locator(".canvas-toolbar")).toHaveCount(1);
    await expect(page.locator(".canvas-corner")).toHaveCount(1);
    const covered = await page.evaluate(() => {
      const results = document.querySelector<HTMLElement>(".search-results")!;
      // What is painted on top, asked of the page: `inert` takes the view out of hit testing (so `elementFromPoint`
      // would look straight through a toolbar drawn over the results), never out of painting, so it is lifted while
      // the points are asked and put back after.
      const view = [...document.querySelectorAll<HTMLElement>("[inert]")];
      for (const element of view) element.inert = false;
      const box = results.getBoundingClientRect();
      const points: [string, number, number][] = [];
      for (const selector of [".canvas-toolbar", ".canvas-corner"]) {
        const r = document.querySelector(selector)!.getBoundingClientRect();
        points.push([selector, r.left + r.width / 2, r.top + r.height / 2]);
      }
      const heading = results.querySelector("h2")!.getBoundingClientRect();
      points.push(["the heading", heading.left + heading.width / 2, heading.top + heading.height / 2]);
      for (let i = 1; i < 10; i++)
        for (let j = 1; j < 10; j++) points.push([`${i},${j}`, box.left + (box.width * i) / 10, box.top + (box.height * j) / 10]);
      const found = points
        .filter(([, x, y]) => !results.contains(document.elementFromPoint(x, y)))
        .map(([what, x, y]) => `${what} (${Math.round(x)},${Math.round(y)}): ${(document.elementFromPoint(x, y) as HTMLElement | null)?.className ?? "nothing"}`);
      for (const element of view) element.inert = true;
      return found;
    });
    expect(covered, "drawn over the results page").toEqual([]);
    // And the page stays under the search box's own suggestions: a new search typed over the results shows them.
    const box = page.getByRole("combobox", { name: "Search entities, identifiers, documents" });
    await box.focus();
    await page.keyboard.type("Ke");
    const option = page.getByRole("option").first();
    await expect(option).toBeVisible();
    const onTop = await option.evaluate((element) => {
      const r = element.getBoundingClientRect();
      return element.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
    });
    expect(onTop, "the suggestions drawn over the results page").toBe(true);
  });
}

// The orchestrator, 15 November 2026: a page opened while a document is read over the view shows at once, the reader
// closed, as the page takes the view's place; focus on the page's heading.
test("a search while a document is read over the view shows the results at once, the reader closed, focus on their heading", async ({ page }) => {
  await page.goto("/keyboard/search-results-harness.html");
  await page.getByRole("button", { name: "Read a document from the graph" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Reading: a document from the graph" })).toBeVisible();
  await page.getByRole("combobox", { name: "Search entities, identifiers, documents" }).focus();
  await page.keyboard.type("Kestrel");
  await page.keyboard.press("Enter");
  const heading = page.getByRole("heading", { name: "Search results for 'Kestrel'" });
  await expect(heading).toBeVisible();
  await expect(page.getByRole("dialog", { name: /^Reading/ })).toHaveCount(0);
  await expect(heading).toBeFocused();
});

test("Ask & Chat opened while a document is read over the view shows its page at once, the reader closed, focus on its heading", async ({ page }) => {
  await page.goto("/keyboard/search-results-harness.html");
  await page.getByRole("button", { name: "Read a document from the graph" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Reading: a document from the graph" })).toBeVisible();
  await page.getByRole("button", { name: "Ask & Chat" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Ask & Chat" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: /^Reading/ })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Ask & Chat" })).toBeFocused();
});

test("Ask & Chat pressed while a document read from an answer is open shows its page in one press, the reader closed, focus on its heading", async ({ page }) => {
  // Case's re-check of 8153cae: the hidden page is not shown, so the opener is not expanded and one press shows it.
  await page.goto("/keyboard/search-results-harness.html?ask=1");
  await page.getByRole("button", { name: "Read a document from an answer" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Reading: a document from an answer" })).toBeVisible();
  const opener = page.getByRole("button", { name: "Ask & Chat" });
  await expect(opener).toHaveAttribute("aria-expanded", "false");
  await opener.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Ask & Chat" })).toBeVisible();
  await expect(page.getByRole("dialog", { name: /^Reading/ })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Ask & Chat" })).toBeFocused();
  await expect(opener).toHaveAttribute("aria-expanded", "true");
});

// v0.6.0 #4 (ADR-145 Amendment 18): Ask & Chat's page sits in the results' place and layer, so the same must hold of it:
// nothing of the Graph beneath (its toolbar, its zoom column) is drawn over any point of the page, in each look; and the
// search box's suggestions stay above it.
for (const [brand, theme] of [["ospreyflow", "dark"], ["ospreyflow", "light"], ["govuk", "light"]] as const) {
  test(`${brand} ${theme}: Ask & Chat's page is drawn over the whole of the view it covers, the canvas's toolbar and zoom column included`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/search-results-harness.html?canvas=1&ask=1${brand === "govuk" ? "&brand=govuk" : ""}`);
    await page.evaluate((chosen) => document.documentElement.setAttribute("data-theme", chosen), theme);
    await expect(page.getByRole("heading", { name: "Ask & Chat" })).toBeVisible();
    await expect(page.locator(".canvas-toolbar")).toHaveCount(1);
    await expect(page.locator(".canvas-corner")).toHaveCount(1);
    const covered = await page.evaluate(() => {
      const ask = document.querySelector<HTMLElement>(".ask-page")!;
      // `inert` takes the view out of hit testing, never out of painting: lifted while the points are asked.
      const view = [...document.querySelectorAll<HTMLElement>("[inert]")];
      for (const element of view) element.inert = false;
      const box = ask.getBoundingClientRect();
      const points: [string, number, number][] = [];
      for (const selector of [".canvas-toolbar", ".canvas-corner"]) {
        const r = document.querySelector(selector)!.getBoundingClientRect();
        points.push([selector, r.left + r.width / 2, r.top + r.height / 2]);
      }
      const heading = ask.querySelector("h2")!.getBoundingClientRect();
      points.push(["the heading", heading.left + heading.width / 2, heading.top + heading.height / 2]);
      for (let i = 1; i < 10; i++)
        for (let j = 1; j < 10; j++) points.push([`${i},${j}`, box.left + (box.width * i) / 10, box.top + (box.height * j) / 10]);
      const found = points
        .filter(([, x, y]) => !ask.contains(document.elementFromPoint(x, y)))
        .map(([what, x, y]) => `${what} (${Math.round(x)},${Math.round(y)}): ${(document.elementFromPoint(x, y) as HTMLElement | null)?.className ?? "nothing"}`);
      for (const element of view) element.inert = true;
      return found;
    });
    expect(covered, "drawn over Ask & Chat's page").toEqual([]);
    const box = page.getByRole("combobox", { name: "Search entities, identifiers, documents" });
    await box.focus();
    await page.keyboard.type("Ke");
    const option = page.getByRole("option").first();
    await expect(option).toBeVisible();
    const onTop = await option.evaluate((element) => {
      const r = element.getBoundingClientRect();
      return element.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
    });
    expect(onTop, "the suggestions drawn over Ask & Chat's page").toBe(true);
  });
}

test("every registered search results action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, SEARCH_RESULTS_ACTIONS);
});
