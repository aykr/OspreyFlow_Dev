// An expansion the working set's cap refuses (rule 2; spec/00 §4: the Glass offers the cap's explicit choices,
// never a cut). The Conduit answers 409 with the typed `limit_exceeded` (`workingset/models.ts`'s
// LimitExceeded). The canvas says it in the over-cap dialog's words, adds nothing, and offers, by keyboard:
// expand by one relationship instead (the cap's *filter*), and save a smaller view of the case (*save_as_view*,
// handed to the App's over-cap dialog, `App.expandCap.test.tsx`). Run as a batch job (*promote_to_batch*,
// ADR-151) is case-b's, drawn when its handler is given. A search's chosen suggestion is drawn three hops out
// (`search/drawSearchResult.ts`), which is how a single choice can reach the cap.
import { expect, type Page, test } from "@playwright/test";

import { CANVAS_CAP_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "CANVAS_CAP_ACTIONS";
const REFUSED = { error: "limit_exceeded", cap_kind: "nodes", cap: 5000, would_be: 6210, options: ["save_as_view", "filter", "promote_to_batch"] };

/** Every count small (under the gate's 500, above what the harness holds), so the gate lets the expansion through, and the Conduit's cap refuses it; then
 * an expansion by one type is answered with a delta. Returns each /expand body sent. */
async function refuseByTheCap(page: Page): Promise<unknown[]> {
  const sent: unknown[] = [];
  await page.route("**/*/expand/preview", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ candidate_node_count: 40, candidate_edge_count: 0, link_count: 2 }) }),
  );
  await page.route("**/*/expand", (route) => {
    const body = route.request().postDataJSON() as { request: { edge_types: string[] | null } };
    sent.push(body);
    return body.request.edge_types === null
      ? route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(REFUSED) })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ delta: { seq: 2, op: "add", nodes: [], edges: [] } }) });
  });
  return sent;
}

async function expandTheFocusedNode(page: Page): Promise<void> {
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("Enter");
}

async function press(page: Page, name: string | RegExp): Promise<void> {
  const button = page.getByRole("alertdialog", { name: "Too large to expand" }).getByRole("button", { name });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

test("an expansion past the cap says the cap's own figure, adds nothing, and is expanded by one relationship instead by keyboard", async ({ page }) => {
  const sent = await refuseByTheCap(page);
  await expandTheFocusedNode(page);
  const refusal = page.getByRole("alertdialog", { name: "Too large to expand" });
  await expect(refusal).toContainText("Too many for the canvas: 6,210 nodes against a limit of 5,000.");
  await expect(refusal).toContainText("Nothing has been added.");
  await expect(page.getByText(/Expand failed \(409\)/)).toHaveCount(0);
  const byType = refusal.getByRole("button", { name: / \([\d,]+\)$/ }).first();
  await expect(byType).toBeVisible();
  await press(page, (await byType.textContent())!);
  await expect.poll(() => sent.length).toBe(2);
  expect((sent[1] as { request: { edge_types: string[] | null } }).request.edge_types).toHaveLength(1);
  await expect(refusal).toHaveCount(0);
  registerCovered(REGISTRY, "narrow-an-over-cap-expansion-by-link-type-by-keyboard");
});

test("an expansion past the cap is saved as a smaller view by keyboard, the cap's figure handed to the App", async ({ page }) => {
  await refuseByTheCap(page);
  await expandTheFocusedNode(page);
  await press(page, "Save a smaller view…");
  type Recorded = { __KEYBOARD__?: { savedSmallerView?: { would_be: number } | null } };
  await expect.poll(() => page.evaluate(() => (window as unknown as Recorded).__KEYBOARD__?.savedSmallerView?.would_be)).toBe(6210);
  await expect(page.getByRole("alertdialog", { name: "Too large to expand" })).toHaveCount(0);
  // Not offered here: the harness gives the canvas no batch handler (case-b's, ADR-151).
  registerCovered(REGISTRY, "save-a-smaller-view-from-an-over-cap-expansion-by-keyboard");
});

test("Escape puts the refusal away and nothing is expanded", async ({ page }) => {
  const sent = await refuseByTheCap(page);
  await expandTheFocusedNode(page);
  const refusal = page.getByRole("alertdialog", { name: "Too large to expand" });
  await expect(refusal).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(refusal).toHaveCount(0);
  expect(sent).toHaveLength(1);
});

// Last in the file: the check reads the cases above it, run in order on one worker.
test("every registered over-cap expansion action has its own proving test case above", () => {
  assertAllCovered(REGISTRY, CANVAS_CAP_ACTIONS);
});
