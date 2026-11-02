// The Matrix view by keyboard alone (`02_GLASS_FRONTEND.md` §6; GDS remediation plan A1; CLAUDE.md
// rule 13): reached from the view switch, walked cell by cell, rows selected and the selection
// carried to the real canvas and back, sorted, paged, and a row's Expand and Show done by the
// canvas itself — Expand proven by the real request it sends.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { assertAllCovered, MATRIX_ACTIONS, registerCovered } from "./actionRegistry";

// The harness opens on the Matrix; every walk here starts on the Graph and reaches it by keyboard.
const HARNESS = "/keyboard/matrix-harness.html?view=graph";

/** Tabs (or Shift+Tabs) until `target` is focused — never a counted number of Tabs. */
async function tabUntilFocused(page: Page, target: Locator, key = "Tab", max = 30): Promise<void> {
  await expect(target).toBeVisible();
  for (let i = 0; i < max && !(await target.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press(key);
  }
  await expect(target).toBeFocused();
}

const viewButton = (page: Page, name: string) =>
  page.getByRole("group", { name: "View" }).getByRole("button", { name, exact: true });
const entities = (page: Page) => page.getByRole("grid", { name: /^Entities in this view/ });
const links = (page: Page) => page.getByRole("grid", { name: /^Links in this view/ });
const rowOf = (grid: Locator, name: RegExp) =>
  grid.getByRole("row").filter({ has: grid.page().getByRole("rowheader", { name }) });
const focusedText = (page: Page) => page.evaluate(() => document.activeElement?.textContent ?? "");
const state = (page: Page) => page.evaluate(() => window.__MATRIX__!);

async function openMatrix(page: Page, query = ""): Promise<void> {
  await page.goto(`${HARNESS}${query.replace(/^\?/, "&")}`);
  await tabUntilFocused(page, viewButton(page, "Matrix"));
  await page.keyboard.press("Enter");
  await expect(viewButton(page, "Matrix")).toHaveAttribute("aria-pressed", "true");
  await expect(entities(page)).toBeVisible();
}

/** Into the entities grid by Tab: its one Tab stop is the Name column's header until a cell is chosen. */
async function intoGrid(page: Page): Promise<void> {
  await tabUntilFocused(page, entities(page).getByRole("button", { name: "Name", exact: true }));
}

async function stubExpansion(page: Page): Promise<{ body: unknown }> {
  const seen: { body: unknown } = { body: null };
  await page.route("**/*/expand/preview", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ candidate_node_count: 1, candidate_edge_count: 0 }),
    }),
  );
  await page.route("**/*/expand", async (route) => {
    seen.body = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] } }),
    });
  });
  return seen;
}

test("the view switch reaches the Matrix, and the arrow keys move between its cells", async ({ page }) => {
  await openMatrix(page);
  // Nothing else stands in for it: the canvas is not drawn while the Matrix is.
  await expect(page.getByRole("application", { name: "Network canvas" })).toHaveCount(0);
  registerCovered("MATRIX_ACTIONS", "reach-the-matrix-view-by-keyboard");

  await intoGrid(page);
  await page.keyboard.press("ArrowDown");
  expect(await focusedText(page)).toBe("+447700900123");
  await page.keyboard.press("ArrowDown");
  expect(await focusedText(page)).toBe("ADEYEMI, Tola");
  await page.keyboard.press("ArrowRight");
  expect(await focusedText(page)).toContain("Person");
  await page.keyboard.press("ArrowRight");
  expect(await focusedText(page)).toBe("OFFICIAL");
  await page.keyboard.press("ArrowRight");
  expect(await focusedText(page)).toBe("Asserted");
  await page.keyboard.press("Home");
  expect(await focusedText(page)).toBe("ADEYEMI, Tola");
  await page.keyboard.press("ArrowDown");
  // The inferred person says so in words (rule 5).
  expect(await focusedText(page)).toBe("BRENNAN, Siobhan");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  expect(await focusedText(page)).toBe("Inferred");
  // One Tab stop: Tab leaves the grid rather than walking its cells.
  await expect(entities(page).locator("[tabindex='0']")).toHaveCount(1);
  registerCovered("MATRIX_ACTIONS", "move-between-cells-by-keyboard");
});

test("Enter selects a row and Space adds one; the canvas opens with that selection", async ({ page }) => {
  await openMatrix(page);
  await intoGrid(page);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown"); // ADEYEMI
  await page.keyboard.press("Enter");
  await expect(rowOf(entities(page), /ADEYEMI/)).toHaveAttribute("aria-selected", "true");
  expect((await state(page)).selection).toEqual(["p2"]);
  registerCovered("MATRIX_ACTIONS", "select-a-row-by-keyboard");

  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown"); // DUCHESNE, whom the cross-filter dims
  expect(await focusedText(page)).toBe("DUCHESNE, MarcDimmed by filter");
  await page.keyboard.press(" ");
  await expect(rowOf(entities(page), /DUCHESNE/)).toHaveAttribute("aria-selected", "true");
  await expect(rowOf(entities(page), /ADEYEMI/)).toHaveAttribute("aria-selected", "true");
  expect((await state(page)).selection).toEqual(["p2", "p4"]);
  registerCovered("MATRIX_ACTIONS", "add-a-row-to-the-selection-by-keyboard");

  // Back to the Graph by keyboard: the real canvas holds the same two.
  await tabUntilFocused(page, viewButton(page, "Graph"), "Shift+Tab");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("application", { name: "Network canvas" })).toBeVisible();
  await expect(page.getByText("2 selected", { exact: true })).toBeVisible();
  expect((await state(page)).selection).toEqual(["p2", "p4"]);
  registerCovered("MATRIX_ACTIONS", "selection-carried-to-the-canvas");
});

test("a selection made on the canvas is selected in the Matrix", async ({ page }) => {
  await page.goto(HARNESS);
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await tabUntilFocused(page, canvas);
  // Reaching the canvas selects its first node (OKAFOR); walk to another and add it with Space.
  await expect.poll(async () => (await state(page)).selection).toEqual(["p1"]);
  await page.keyboard.press("Control+Shift+ArrowRight");
  await page.keyboard.press(" ");
  await expect.poll(async () => (await state(page)).selection.length).toBe(2);
  const [, second] = (await state(page)).selection;

  await tabUntilFocused(page, viewButton(page, "Matrix"), "Shift+Tab");
  await page.keyboard.press("Enter");
  await expect(rowOf(entities(page), /OKAFOR/)).toHaveAttribute("aria-selected", "true");
  const selectedRows = entities(page).locator("tbody tr[aria-selected='true']");
  await expect(selectedRows).toHaveCount(2);
  expect(second).not.toBe("p1");
  registerCovered("MATRIX_ACTIONS", "canvas-selection-carried-to-the-matrix");
});

test("a column header sorts by keyboard, and says which way", async ({ page }) => {
  await openMatrix(page);
  await intoGrid(page);
  const name = entities(page).getByRole("columnheader", { name: "Name" });
  await expect(name).toHaveAttribute("aria-sort", "ascending");
  await page.keyboard.press("Enter");
  await expect(name).toHaveAttribute("aria-sort", "descending");
  await expect(entities(page).getByRole("rowheader").first()).toHaveText("OKAFOR, Callum");
  for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
  expect(await focusedText(page)).toBe("Links in view");
  await page.keyboard.press("Enter");
  await expect(entities(page).getByRole("columnheader", { name: "Links in view" })).toHaveAttribute("aria-sort", "descending");
  await expect(name).not.toHaveAttribute("aria-sort", /.+/);
  await expect(entities(page).locator("caption")).toContainText("Sorted by links in view, most first.");
  registerCovered("MATRIX_ACTIONS", "sort-a-column-by-keyboard");
});

test("Page Down and Page Up turn the page, and the caption says which rows are shown", async ({ page }) => {
  await openMatrix(page, "?many=1");
  const caption = entities(page).locator("caption");
  await expect(caption).toContainText("Rows 1 to 100 of 255.");
  await intoGrid(page);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("PageDown");
  await expect(caption).toContainText("Rows 101 to 200 of 255.");
  // Focus stays in the grid, on the same row of the new page.
  expect(await page.evaluate(() => document.activeElement?.closest("table")?.getAttribute("role"))).toBe("grid");
  await page.keyboard.press("PageDown");
  await expect(caption).toContainText("Rows 201 to 255 of 255.");
  await page.keyboard.press("PageUp");
  await expect(caption).toContainText("Rows 101 to 200 of 255.");
  registerCovered("MATRIX_ACTIONS", "turn-the-page-by-keyboard");
});

test("a link row is selected by keyboard", async ({ page }) => {
  await openMatrix(page);
  await tabUntilFocused(page, links(page).getByRole("button", { name: "Link", exact: true }));
  await page.keyboard.press("ArrowDown");
  // Sorted by From: ADEYEMI's link to DUCHESNE comes first.
  await page.keyboard.press("Enter");
  expect((await state(page)).selectedEdge).toBe("l4");
  await expect(links(page).locator("tbody tr").first()).toHaveAttribute("aria-selected", "true");
  expect((await state(page)).selection).toEqual([]);
  registerCovered("MATRIX_ACTIONS", "select-a-link-row-by-keyboard");
});

test("Expand on a row expands it on the canvas — a real request, through the canvas's preview", async ({ page }) => {
  const seen = await stubExpansion(page);
  await openMatrix(page);
  await intoGrid(page);
  for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowDown"); // OKAFOR
  await page.keyboard.press("End");
  await page.keyboard.press("ArrowLeft");
  expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-label"))).toBe("Expand OKAFOR, Callum");
  await page.keyboard.press("Enter");
  await expect(viewButton(page, "Graph")).toHaveAttribute("aria-pressed", "true");
  await expect.poll(() => seen.body !== null).toBe(true);
  expect(seen.body).toMatchObject({ request: { node_ids: ["p1"], depth: 1 } });
  registerCovered("MATRIX_ACTIONS", "expand-from-a-row-by-keyboard");
});

test("Show on a row opens the Graph with that node selected", async ({ page }) => {
  await openMatrix(page);
  await intoGrid(page);
  for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowDown"); // BRENNAN
  await page.keyboard.press("End");
  expect(await page.evaluate(() => document.activeElement?.getAttribute("aria-label"))).toBe(
    "Show BRENNAN, Siobhan on the graph",
  );
  await page.keyboard.press("Enter");
  await expect(page.getByRole("application", { name: "Network canvas" })).toBeVisible();
  await expect(page.getByText("1 selected", { exact: true })).toBeVisible();
  expect((await state(page)).selection).toEqual(["p3"]);
  registerCovered("MATRIX_ACTIONS", "show-a-row-on-the-graph-by-keyboard");
});

test("the link table sorts by connection strength and by rarity, by keyboard (ADR-139)", async ({ page }) => {
  await openMatrix(page, "?strength=1");
  await tabUntilFocused(page, links(page).getByRole("button", { name: "Link", exact: true }));
  for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowRight");
  expect(await focusedText(page)).toBe("Strength");
  // A number sorts most first at the first press, as "Links in view" does.
  await page.keyboard.press("Enter");
  await expect(links(page).getByRole("columnheader", { name: "Strength" })).toHaveAttribute("aria-sort", "descending");
  // The strongest first: OKAFOR's Endpoint link (0.88).
  await expect(links(page).locator("tbody tr").first()).toContainText("0.88");
  await page.keyboard.press("ArrowRight");
  expect(await focusedText(page)).toBe("Rarity");
  await page.keyboard.press("Enter");
  await expect(links(page).getByRole("columnheader", { name: "Rarity" })).toHaveAttribute("aria-sort", "descending");
  // The rarest pairing first: OKAFOR and ADEYEMI (2.40); a pairing with none worked out is last.
  await expect(links(page).locator("tbody tr").first()).toContainText("2.40");
  await expect(links(page).locator("tbody tr").last()).toContainText("None");
  registerCovered("MATRIX_ACTIONS", "sort-links-by-strength-and-rarity-by-keyboard");
});

test("every Matrix keyboard action has a proving case", () => {
  assertAllCovered("MATRIX_ACTIONS", MATRIX_ACTIONS);
});
