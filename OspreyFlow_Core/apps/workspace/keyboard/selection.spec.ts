// The selection, by keyboard alone (ADR-093, ADR-097, rule 13): the selection bar's Clear, Remove
// from view and Expand, and the Inspector list's Centre and Remove, each against the real canvas.
// No `page.mouse`, no `.click()`.
import { expect, test, type Page } from "@playwright/test";

import { SELECTION_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

declare global {
  interface Window {
    __KEYBOARD__?: { focused: string | null; selection: string[] };
  }
}

const selection = (page: Page) => page.evaluate(() => window.__KEYBOARD__?.selection ?? []);
const focused = (page: Page) => page.evaluate(() => window.__KEYBOARD__?.focused ?? null);

async function tabTo(page: Page, name: RegExp, max = 30) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const text = await page.evaluate(
      () => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent ?? "",
    );
    if (name.test(text)) return;
  }
  throw new Error(`Tab never reached ${String(name)}`);
}

/** n0 is selected on focus; ArrowRight moves to a neighbour and Space adds it. */
async function selectTwo(page: Page) {
  await page.goto("/keyboard/harness.html");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  await expect.poll(() => selection(page)).toEqual(["n0"]);
  await page.keyboard.press("ArrowRight");
  await expect.poll(() => focused(page)).not.toBe("n0");
  const second = await focused(page);
  await page.keyboard.press(" ");
  await expect.poll(() => selection(page)).toEqual(["n0", second]);
  return second as string;
}

test("the selection bar says how many once, and its Clear empties the selection", async ({ page }) => {
  await selectTwo(page);
  const bar = page.getByRole("toolbar", { name: "Selection" });
  await expect(bar.getByRole("status")).toHaveText("2 selected");
  await expect(page.getByText(/\d+ selected/)).toHaveCount(1); // one live count in the page
  await bar.getByRole("button", { name: "Clear", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => selection(page)).toEqual([]);
  await expect(page.getByRole("toolbar", { name: "Selection" })).toHaveCount(0);
  registerCovered("SELECTION_ACTIONS", "clear-the-selection-from-the-selection-bar");
});

test("the selection bar's Remove from view takes the selected nodes out, through a real DELETE", async ({ page }) => {
  let body: { node_ids: string[] } | null = null;
  await page.route("**/*/investigations/*/nodes", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ seq: 7 }) });
  });
  const second = await selectTwo(page);
  await page.getByRole("toolbar", { name: "Selection" }).getByRole("button", { name: "Remove from view" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => body?.node_ids.slice().sort()).toEqual(["n0", second].sort());
  registerCovered("SELECTION_ACTIONS", "remove-the-selection-from-the-selection-bar");
});

test("the selection bar's Show links among these asks for the links among the selected nodes (ADR-098)", async ({ page }) => {
  let body: { node_ids: string[] | null } | null = null;
  await page.route("**/*/investigations/*/links-among", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ added: 0, delta: { seq: 8, op: "add", nodes: [], edges: [] } }),
    });
  });
  const second = await selectTwo(page);
  await page.getByRole("toolbar", { name: "Selection" }).getByRole("button", { name: "Show links among these" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => body?.node_ids?.slice().sort()).toEqual(["n0", second].sort());
  await expect(page.getByText("No more links among these.")).toBeVisible();
  registerCovered("SELECTION_ACTIONS", "show-links-among-the-selection-from-the-selection-bar");
});

test("the selection bar's Ask the model about these… branches the selection, named for its documents, and opens it (ADR-098)", async ({ page }) => {
  let body: { node_ids: string[]; name?: string } | null = null;
  await page.route("**/*/investigations/*/branch", async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "branch-q", name: "Questions on 1 document" }),
    });
  });
  await page.goto("/keyboard/harness.html?fixture=emails");
  await page.getByRole("application", { name: "Network canvas" }).focus();
  const bar = page.getByRole("toolbar", { name: "Selection" });
  // A selection with no Document is not offered it.
  await expect.poll(() => selection(page)).not.toEqual([]);
  await expect(bar.getByRole("button", { name: "Ask the model about these…" })).toHaveCount(0);
  for (let i = 0; i < 8; i++) {
    if ((await focused(page)) === "email:ev-1") break;
    await page.keyboard.press("Control+Shift+ArrowRight"); // every node in turn, linked or not
  }
  await expect.poll(() => focused(page)).toBe("email:ev-1");
  await page.keyboard.press(" ");
  await expect.poll(() => selection(page)).toContain("email:ev-1");
  await bar.getByRole("button", { name: "Ask the model about these…" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => body?.name).toBe("Questions on 1 document");
  expect(body!.node_ids).toContain("email:ev-1");
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __KEYBOARD__?: { askedIn?: string | null } }).__KEYBOARD__?.askedIn))
    .toBe("branch-q");
  registerCovered("SELECTION_ACTIONS", "ask-the-model-about-the-selected-documents-from-the-selection-bar");
});

test("the selection bar's Expand asks to expand each selected node", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/expand")) asked.push(request.url());
  });
  await selectTwo(page);
  await page.getByRole("toolbar", { name: "Selection" }).getByRole("button", { name: "Expand" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => asked.length).toBeGreaterThan(0);
  registerCovered("SELECTION_ACTIONS", "expand-the-selection-from-the-selection-bar");
});

test("the list's name centres on that node and leaves the selection as it was", async ({ page }) => {
  await selectTwo(page);
  await expect(page.getByRole("heading", { name: "Selected (2)" })).toBeVisible();
  await tabTo(page, /^Centre on n0/);
  await page.keyboard.press("Enter");
  await expect.poll(() => focused(page)).toBe("n0");
  expect(await selection(page)).toHaveLength(2);
  registerCovered("SELECTION_ACTIONS", "centre-on-a-selected-node-from-the-list");
});

test("the list's × takes that node out of the selection", async ({ page }) => {
  const second = await selectTwo(page);
  await tabTo(page, new RegExp(`^Remove ${second} from the selection$`));
  await page.keyboard.press("Enter");
  await expect.poll(() => selection(page)).toEqual(["n0"]);
  registerCovered("SELECTION_ACTIONS", "remove-a-node-from-the-selection-from-the-list");
});

test("every registered selection action has its own proving test case above", () => {
  assertAllCovered("SELECTION_ACTIONS", SELECTION_ACTIONS);
});
