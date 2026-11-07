// ADR-145 Amendment 2 §5: the parts the right-hand column shows, counted on the real panels (each
// mounted by its own harness), not the prototype's stand-in. Variant B opens the column with the
// Inspector alone, so it shows the Inspector's parts — at most 7 for a node, 6 for a link — where
// the column with every panel open showed the Inspector's, Metrics' 3 and the Query builder's 3: at
// most 13. (The prototype's stand-in said 8 and 15.)
import { expect, test, type Page } from "@playwright/test";

/** The panel's part headers once it has finished drawing (some parts, Metrics' Legend among them,
 * arrive with the panel's first read): read until two reads half a second apart agree. */
async function parts(page: Page, harness: string): Promise<string[]> {
  await page.goto(`/keyboard/${harness}`);
  const headers = page.locator(".accordion-section__header");
  await expect(headers.first()).toBeVisible();
  const read = () => headers.evaluateAll((els) => els.map((e) => (e.textContent || "").trim()));
  let last = await read();
  for (let i = 0; i < 10; i++) {
    await page.waitForTimeout(500);
    const now = await read();
    if (now.join("|") === last.join("|")) return now;
    last = now;
  }
  return last;
}

test("the real panels' parts: the Inspector's for a node and a link, Metrics' and the Query builder's", async ({ page }) => {
  const node = await parts(page, "inspector-harness.html?view=node");
  expect(node).toEqual(["Properties", "Relationships", "Shares contacts", "Neighbourhood risk", "Provenance", "Source"]);
  const pictured = await parts(page, "inspector-harness.html?view=picture");
  expect(pictured).toEqual(["Properties", "Picture", "Relationships", "Provenance", "Source"]);
  // A node with a picture and every right shows every one of them: at most 7.
  expect(new Set([...node, ...pictured]).size).toBe(7);
  expect(await parts(page, "inspector-harness.html")).toHaveLength(6); // a link
  const metrics = await parts(page, "metrics-panel-harness.html");
  expect(metrics).toEqual(["Ranking", "Community detection", "Filter"]);
  const query = await parts(page, "query-builder-harness.html");
  expect(query).toEqual(["Pattern", "Add to the pattern", "Save and load"]);
  // The column with every panel open, for a node with a picture: 7 + 3 + 3 = 13; variant B, 7.
  expect(new Set([...node, ...pictured]).size + metrics.length + query.length).toBe(13);
});
