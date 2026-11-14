// An expansion the working set's cap refuses (rule 2; spec/00 §4: the Glass offers the cap's explicit choices,
// never a cut). The Conduit answers 409 with the typed `limit_exceeded` (`workingset/models.ts`'s
// LimitExceeded, the body `services/api/app.py` sends). The canvas says it in the over-cap dialog's words, adds
// nothing, and offers, by keyboard: expand by one relationship instead (the cap's *filter*), and save a smaller
// view of the case (*save_as_view*, handed to the App's over-cap dialog, `App.expandCap.test.tsx`). Run as a batch
// job (*promote_to_batch*, ADR-151) is case-b's: its slot is proven here, its job there. A 409 that is not the cap's
// stays the expansion's failure. A search's chosen suggestion is drawn three hops out (`search/drawSearchResult.ts`),
// which is how a single choice can reach the cap.
import { expect, type Page, test } from "@playwright/test";

import { CANVAS_CAP_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "CANVAS_CAP_ACTIONS";
const REFUSED = { error: "limit_exceeded", cap_kind: "nodes", cap: 5000, would_be: 6210, options: ["save_as_view", "filter", "promote_to_batch"] };
type Body = { request: { edge_types: string[] | null } };
type Recorded = {
  __KEYBOARD__?: {
    savedSmallerView?: { would_be: number } | null;
    batchRequested?: { nodeId: string; edgeType: string | null; depth: number; would_be: number } | null;
  };
};

/** Every count small (under the gate's 500, above what the harness holds), so the gate lets the expansion
 * through. `/expand` answers `refuse(body)`: the cap's 409 for every expansion by default; a delta where it
 * answers null. Returns each /expand body sent. */
async function answerExpansions(page: Page, refuse: (body: Body) => { status: number; body: string } | null = () => ({ status: 409, body: JSON.stringify(REFUSED) })): Promise<Body[]> {
  const sent: Body[] = [];
  await page.route("**/*/expand/preview", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ candidate_node_count: 40, candidate_edge_count: 0, link_count: 2 }) }),
  );
  await page.route("**/*/expand", (route) => {
    const body = route.request().postDataJSON() as Body;
    sent.push(body);
    const answer = refuse(body);
    return answer
      ? route.fulfill({ status: answer.status, contentType: "application/json", body: answer.body })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] } }) });
  });
  return sent;
}

/** The cap refuses an expansion by every type; one by a single type goes through. */
const refuseTheWhole = (body: Body) => (body.request.edge_types === null ? { status: 409, body: JSON.stringify(REFUSED) } : null);

async function expandTheFocusedNode(page: Page, query = ""): Promise<void> {
  await page.goto(`/keyboard/harness.html${query}`);
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("Enter");
}

const refusal = (page: Page) => page.getByRole("alertdialog", { name: "Too large to expand" });

/** Reaches a choice by Tab from where the refusal puts focus (its first button), as a keyboard user does,
 * and presses Enter on it. */
async function reachAndPress(page: Page, name: string): Promise<void> {
  const button = refusal(page).getByRole("button", { name, exact: true });
  await expect(button, `the refusal offers no ${name}`).toHaveCount(1);
  await expect.poll(() => refusal(page).evaluate((el) => el.contains(document.activeElement))).toBe(true);
  for (let i = 0; i < 20 && !(await button.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(button, `${name} was not reached by Tab`).toBeFocused();
  await page.keyboard.press("Enter");
}

test("an expansion past the cap says the cap's own figure, adds nothing, and is expanded by one relationship instead by keyboard", async ({ page }) => {
  const sent = await answerExpansions(page, refuseTheWhole);
  await expandTheFocusedNode(page);
  await expect(refusal(page)).toContainText("Too many for the canvas: 6,210 nodes against a limit of 5,000.");
  await expect(refusal(page)).toContainText("Nothing has been added.");
  await expect(page.getByText(/Expand failed \(409\)/)).toHaveCount(0);
  // The last relationship offered, not the first: a choice that always sent the first would be caught.
  const offered = refusal(page).getByRole("button", { name: / \([\d,]+\)$/ });
  await expect(offered.first()).toBeVisible();
  expect(await offered.count()).toBeGreaterThan(1);
  const label = (await offered.last().textContent())!;
  await reachAndPress(page, label);
  await expect.poll(() => sent.length).toBe(2);
  // Named by its type's own words where the schema gives no label (`linkLabel.ts`).
  const type = label.replace(/ \([\d,]+\)$/, "").toUpperCase().replace(/ /g, "_");
  expect(sent[1]!.request.edge_types).toEqual([type]);
  await expect(refusal(page)).toHaveCount(0);
  registerCovered(REGISTRY, "narrow-an-over-cap-expansion-by-link-type-by-keyboard");
});

test("an expansion past the cap is saved as a smaller view by keyboard, the cap's figure handed to the App", async ({ page }) => {
  await answerExpansions(page);
  await expandTheFocusedNode(page);
  await reachAndPress(page, "Save a smaller view…");
  await expect.poll(() => page.evaluate(() => (window as unknown as Recorded).__KEYBOARD__?.savedSmallerView?.would_be)).toBe(6210);
  await expect(refusal(page)).toHaveCount(0);
  // Not offered here: the harness gives the canvas no batch handler unless asked (?batch=1).
  await expect(page.getByRole("button", { name: "Run as a batch job" })).toHaveCount(0);
  registerCovered(REGISTRY, "save-a-smaller-view-from-an-over-cap-expansion-by-keyboard");
});

test("an expansion by one link type the cap refuses offers no narrowing, and the save still", async ({ page }) => {
  await answerExpansions(page);
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("\\");
  const byType = page.locator(".radial-menu__list[role='menu']").getByRole("group", { name: "Expand by link type" }).getByRole("menuitem").first();
  await byType.focus();
  await page.keyboard.press("Enter");
  await expect(refusal(page)).toContainText("Too many for the canvas: 6,210 nodes against a limit of 5,000.");
  await expect(refusal(page)).toContainText("Nothing has been added.");
  await expect(refusal(page).getByText("Expand by one relationship instead:")).toHaveCount(0);
  await expect(refusal(page).getByRole("button", { name: "Save a smaller view…" })).toBeVisible();
});

test("Run as a batch job hands the refused expansion up, when the canvas is given a handler (ADR-151's slot)", async ({ page }) => {
  await answerExpansions(page);
  await expandTheFocusedNode(page, "?batch=1");
  await reachAndPress(page, "Run as a batch job");
  const asked = await page.evaluate(() => (window as unknown as Recorded).__KEYBOARD__?.batchRequested ?? null);
  expect(asked).toMatchObject({ edgeType: null, depth: 1, would_be: 6210 });
  expect(asked!.nodeId).toBeTruthy();
  await expect(refusal(page)).toHaveCount(0);
});

for (const [what, answer] of [
  ["a 409 that is not the cap's", { status: 409, body: JSON.stringify({ error: "conflict" }) }],
  ["a 409 whose body is not JSON", { status: 409, body: "Conflict" }],
] as const) {
  test(`${what} stays the expansion's failure, never the cap's refusal`, async ({ page }) => {
    await answerExpansions(page, () => answer);
    await expandTheFocusedNode(page);
    await expect(page.getByText("Expand failed (409). Try again.")).toBeVisible();
    await expect(refusal(page)).toHaveCount(0);
  });
}

test("a node taken out while its refusal is open takes the refusal with it, and is never expanded back", async ({ page }) => {
  const sent = await answerExpansions(page, refuseTheWhole);
  await expandTheFocusedNode(page);
  await expect(refusal(page)).toBeVisible();
  type Canvas = { __CANVAS__?: { removeNode?: (id: string) => void; hasNode: (id: string) => boolean }; __KEYBOARD__?: { focused: string | null } };
  const node = await page.evaluate(() => (window as unknown as Canvas).__KEYBOARD__?.focused ?? null);
  expect(node).toBeTruthy();
  await page.evaluate((id) => (window as unknown as Canvas).__CANVAS__!.removeNode!(id), node!);
  await expect.poll(() => page.evaluate((id) => (window as unknown as Canvas).__CANVAS__!.hasNode(id), node!)).toBe(false);
  await expect(refusal(page)).toHaveCount(0);
  expect(sent).toHaveLength(1);
});

test("Escape puts the refusal away and nothing is expanded", async ({ page }) => {
  const sent = await answerExpansions(page);
  await expandTheFocusedNode(page);
  await expect(refusal(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(refusal(page)).toHaveCount(0);
  expect(sent).toHaveLength(1);
});

// Last in the file: the check reads the cases above it, run in order on one worker.
test("every registered over-cap expansion action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, CANVAS_CAP_ACTIONS);
});
