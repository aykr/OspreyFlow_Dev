// ADR-119 on the 50k-node / 250k-link fixture: a working set of more than 10,000 links opens
// grouped by community, and zoomed out it draws one link between each pair of communities instead
// of every link, and each ordinary node as a dot; from the neighbourhood band in, every link and
// every node is drawn in full again. Zoom never changes what
// exists: a link selected while zoomed out is drawn.
import { expect, test, type Page } from "@playwright/test";

/** How many pixels the community-link layer has drawn now. */
async function communityInk(page: Page): Promise<number> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>("canvas.sigma-communityLinks");
    if (!canvas) return -1;
    const data = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let drawn = 0;
    for (let i = 3; i < data.length; i += 4) if (data[i]! > 0) drawn += 1;
    return drawn;
  });
}

test("a large working set opens grouped by community, its links between communities drawn until zoomed in", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.goto("/perf/harness.html");
  await page.waitForFunction(() => window.__PERF__?.readyAt != null, undefined, { timeout: 90_000 });

  // Grouped by community once the worker has answered, and the links between communities drawn.
  await expect(page.getByRole("combobox").first()).toHaveValue("bubbles", { timeout: 60_000 });
  await expect.poll(() => communityInk(page), { timeout: 30_000 }).toBeGreaterThan(1000);
  // At the fitted view (the structure band) no individual link is drawn.
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.linkDrawn("e0")), { timeout: 30_000 }).toBe(false);

  // Zoomed out, an ordinary node is a dot; a selected one is drawn in full.
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.nodeDrawnAs("n0")), { timeout: 30_000 }).toBe("dot");
  await page.evaluate(() => window.__CANVAS__?.highlightNodes(["n0"]));
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.nodeDrawnAs("n0")), { timeout: 30_000 }).toBe("full");
  await page.evaluate(() => window.__CANVAS__?.highlightNodes([]));

  // A link selected while zoomed out is drawn.
  await page.evaluate(() => window.__CANVAS__?.selectLink("e0"));
  // A refresh of 250,000 links' looks takes seconds under software rendering.
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.linkDrawn("e0")), { timeout: 30_000 }).toBe(true);
  await page.evaluate(() => window.__CANVAS__?.selectLink(null));

  // Zoomed in to the neighbourhood band: every link is drawn, and the layer is clear.
  await page.evaluate(() => window.__CANVAS__?.zoomTo(0.3));
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.linkDrawn("e1")), { timeout: 30_000 }).toBe(true);
  await expect.poll(() => communityInk(page), { timeout: 30_000 }).toBe(0);
  await expect.poll(() => page.evaluate(() => window.__CANVAS__?.nodeDrawnAs("n1")), { timeout: 30_000 }).toBe("full");
});
