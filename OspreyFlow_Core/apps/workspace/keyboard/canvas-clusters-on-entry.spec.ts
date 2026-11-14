// Step 3h (ADR-124 Amendment 19; rule 6, "collapses them at query time"): a seed's or an expansion's answer carries
// the cluster each of the reader's own nodes is in at the case's τ (`clusters`, for them alone), and the canvas
// applies it after the add. Before, cluster ids came only when a threshold move changed a cluster, so a pair already
// merged never read as one: Explain cluster was never offered for it, and its members were not drawn together (found
// live, `process/lanes/case/gates/live-redesign/RECORD.md`). Its own answer, never a change of the resolution: a
// fold made from a same-as link stays folded.
import { expect, type Page, test } from "@playwright/test";

type W = { __CANVAS__?: { viewportPositionOf: (id: string) => { x: number; y: number } | null } };

async function expandAnsweredWithClusters(page: Page, clusters: Record<string, string>): Promise<void> {
  await page.route("**/*/expand/preview", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ candidate_node_count: 40, candidate_edge_count: 0, link_count: 0 }) }),
  );
  await page.route("**/*/expand", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        delta: { seq: 2, op: "add", nodes: [], edges: [] },
        clusters: { seq: 2, op: "reproject", reason: "resolution_on_entry", affected_cluster_ids: clusters },
      }),
    }),
  );
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus(); // n0
  await page.keyboard.press("Enter");
}

test("an expansion's own clusters are applied: Explain cluster is offered on a pair already merged", async ({ page }) => {
  await expandAnsweredWithClusters(page, { n0: "n0", n1: "n0" });
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await expect
    .poll(async () => {
      await canvas.focus();
      await page.keyboard.press("\\");
      const offered = await page.locator(".radial-menu__list[role='menu']").getByRole("menuitem", { name: "Explain cluster" }).count();
      await page.keyboard.press("Escape");
      return offered;
    }, { timeout: 15_000 })
    .toBe(1);
});

test("an expansion's own clusters draw a pair already merged together, on its anchor", async ({ page }) => {
  await expandAnsweredWithClusters(page, { n0: "n0", n1: "n0" });
  const at = (id: string) => page.evaluate((n) => (window as unknown as W).__CANVAS__!.viewportPositionOf(n), id);
  // Both read together each time: the anchor itself may still be moving into place.
  await expect.poll(async () => JSON.stringify(await at("n1")) === JSON.stringify(await at("n0")), { timeout: 15_000 }).toBe(true);
});

test("a fold made from a same-as link stays folded when an expansion's own clusters arrive", async ({ page }) => {
  // Its own clusters are not a change of the resolution: only a threshold move or a manual decision opens the
  // folds made from same-as links ("The resolution changed, so the nodes you collapsed are shown again.").
  await page.route("**/*/expand/preview", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ candidate_node_count: 40, candidate_edge_count: 0, link_count: 0 }) }),
  );
  await page.route("**/*/expand", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        delta: { seq: 2, op: "add", nodes: [], edges: [] },
        clusters: { seq: 2, op: "reproject", reason: "resolution_on_entry", affected_cluster_ids: { s0: "s0", s1: "s0" } },
      }),
    }),
  );
  type G = { __GROUPED__?: number; __KEYBOARD__?: { selectedEdge: string | null }; __CANVAS__?: { expandNode: (id: string) => void } };
  await page.goto("/keyboard/harness.html?fixture=same-as");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("l");
  await expect.poll(() => page.evaluate(() => (window as unknown as G).__KEYBOARD__?.selectedEdge)).toBe("sa0");
  await page.keyboard.press("\\");
  await expect(page.getByRole("menuitem", { name: "Collapse into one node" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => (window as unknown as G).__GROUPED__)).toBe(3);

  const expanded = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith("/expand"));
  await page.evaluate(() => (window as unknown as G).__CANVAS__!.expandNode("s0"));
  await expanded;
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => (window as unknown as G).__GROUPED__)).toBe(3);
  await expect(page.getByText("The resolution changed, so the nodes you collapsed are shown again.")).toHaveCount(0);
});
