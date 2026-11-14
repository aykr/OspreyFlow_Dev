// An expansion whose nodes the case's stream draws before the expansion's own answer arrives. The Conduit
// publishes the add on the stream as it answers, and the stream can win: found live on 14 November 2026, where
// fixture-corp's Same as expansion added four people and the canvas said "Nothing new: everything linked by
// ‘Same as’ is already in view." That notice then held the canvas's keys, so the next menu never opened. What
// is new is what the canvas did not hold when the expansion was asked for, not when its answer lands.
import { expect, test } from "@playwright/test";

type W = { __CANVAS__?: { landCopy?: (fromId: string, newId: string) => unknown; hasNode: (id: string) => boolean } };

test("nodes the stream drew first are still the expansion's own: no 'Nothing new'", async ({ page }) => {
  await page.route("**/*/expand/preview", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ candidate_node_count: 1, candidate_edge_count: 0, link_count: 0 }) }),
  );
  await page.route("**/*/expand", async (route) => {
    // The stream's add lands first, then the answer carrying the same node.
    const node = await page.evaluate(() => (window as unknown as W).__CANVAS__!.landCopy!("n1", "n-new"));
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ delta: { seq: 3, op: "add", nodes: [node], edges: [] } }) });
  });
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  const answered = page.waitForResponse((r) => new URL(r.url()).pathname.endsWith("/expand"));
  await page.keyboard.press("Enter");
  await answered;
  await expect.poll(() => page.evaluate(() => (window as unknown as W).__CANVAS__!.hasNode("n-new"))).toBe(true);
  await page.waitForTimeout(300);
  await expect(page.getByText(/^Nothing new/)).toHaveCount(0);
});
