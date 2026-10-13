// What the canvas paints, read from the pixels (ADR-097 step 2, design review item 9). A node's size
// is a number handed to Sigma; this checks the number becomes 14 painted pixels across at 100%.
import { expect, test, type Page } from "@playwright/test";

import { layoutSettled } from "./layoutSettled";
import { readPng } from "./pngPixels";

declare global {
  interface Window {
    __CANVAS__?: {
      viewportPositionOf: (nodeId: string) => { x: number; y: number } | null;
      zoomTo: (ratio: number) => void;
    };
  }
}

/** The painted width of `nodeId` along a row and down a column through its centre, in CSS pixels:
 * from its edge on one side to its edge on the other against the bare canvas. The smaller of the
 * two, since a link leaving the node lengthens the run along its own direction. */
async function paintedDiameter(page: Page, nodeId: string): Promise<number> {
  const canvas = page.getByRole("application", { name: "Network canvas" });
  const box = (await canvas.boundingBox())!;
  const at = await page.evaluate((id) => window.__CANVAS__?.viewportPositionOf(id) ?? null, nodeId);
  if (!at) throw new Error("the node is not drawn");
  // The node alone on the bare canvas: the toolbar, the controls and the grid would otherwise be read
  // as the node's edge, or as its background, wherever the layout put it.
  await page.addStyleTag({
    content:
      "button, select, label, .canvas-toolbar, .canvas-legend, .canvas-zoom { visibility: hidden !important; } .network-canvas { background-image: none !important; }",
  });
  const pixels = readPng(await page.screenshot());
  const scale = pixels.width / page.viewportSize()!.width;
  const cx = Math.round((box.x + at.x) * scale);
  const cy = Math.round((box.y + at.y) * scale);
  const near = (a: number[], b: number[]) => Math.abs(a[0]! - b[0]!) + Math.abs(a[1]! - b[1]!) + Math.abs(a[2]! - b[2]!) < 24;
  // The bare canvas's colour, from a corner nothing is drawn in (the toolbar and grid are hidden); a
  // point beside the node can fall on one of its links.
  const background = pixels.at(Math.round((box.x + 4) * scale), Math.round((box.y + 40) * scale));
  // From 30px out, towards the centre, to the first pixel unlike the canvas: the node's edge. Coming
  // in from outside, so whatever is drawn inside the node (its icon) cannot end the run early.
  const edge = (dx: number, dy: number) => {
    const reach = Math.round(30 * scale);
    for (let out = reach; out > 0; out--) {
      if (!near(pixels.at(cx + dx * out, cy + dy * out), background)) return out;
    }
    return 0;
  };
  const across = edge(1, 0) + edge(-1, 0) + 1;
  const down = edge(0, 1) + edge(0, -1) + 1;
  return Math.min(across, down) / scale;
}

// DESIGN.md v0.3 §5a, ADR-115 Amendment 1: 14px across at 100%.
test("a node is 14 pixels across at 100%", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  // Measured once the layout has stopped moving the node (`layoutSettled.ts`), at 100%.
  await layoutSettled(page, ["n3"]);
  await page.evaluate(() => window.__CANVAS__?.zoomTo(1));
  await layoutSettled(page, ["n3"]);
  const diameter = await paintedDiameter(page, "n3");
  expect(diameter).toBeGreaterThanOrEqual(12);
  expect(diameter).toBeLessThanOrEqual(17);
});

// ADR-115 Amendment 1: a node drawn 14px across is clicked on anywhere in a 24×24 area round it, so
// a click just off its painted edge still selects it; one well clear of it selects nothing.
test("a click just beside a node selects it, and one well clear of it does not", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await layoutSettled(page, ["n4"]);
  await page.evaluate(() => window.__CANVAS__?.zoomTo(1));
  const at = (await layoutSettled(page, ["n4"]))["n4"]!;
  const canvas = page.getByRole("application", { name: "Network canvas" });
  const box = (await canvas.boundingBox())!;
  // Read with the controls and grid hidden, as `paintedDiameter` does; shown again to click.
  const hide = await page.addStyleTag({
    content:
      "button, select, label, .canvas-toolbar, .canvas-legend, .canvas-zoom { visibility: hidden !important; } .network-canvas { background-image: none !important; }",
  });
  const pixels = readPng(await page.screenshot());
  const scale = pixels.width / page.viewportSize()!.width;
  const background = pixels.at(Math.round((box.x + 4) * scale), Math.round((box.y + 40) * scale));
  const bare = (x: number, y: number) => {
    const p = pixels.at(Math.round((box.x + x) * scale), Math.round((box.y + y) * scale));
    return Math.abs(p[0]! - background[0]!) + Math.abs(p[1]! - background[1]!) + Math.abs(p[2]! - background[2]!) < 24;
  };
  // 10px out along an axis with nothing drawn there: past the 7px radius and the square the renderer
  // picks within (a diagonal's corner is still inside that square), inside the 12px reach.
  // Bare all the way out to the far click, so neither lands on a link the renderer would take first.
  const side = [[1, 0], [-1, 0], [0, 1], [0, -1]].find(([dx, dy]) =>
    [9, 10, 12, 14, 16, 18, 20].every((out) => bare(at.x + dx! * out, at.y + dy! * out)),
  );
  await hide.evaluate((tag) => tag.remove());
  expect(side, "a bare side of the node").toBeDefined();
  const [dx, dy] = side!;
  const selection = () => page.evaluate(() => window.__KEYBOARD__?.selection ?? []);
  await canvas.click({ position: { x: at.x + dx! * 10, y: at.y + dy! * 10 } });
  await expect.poll(selection).toEqual(["n4"]);
  // On empty space it clears the selection; after a pause, or the renderer reads a double-click.
  await page.waitForTimeout(500);
  await canvas.click({ position: { x: at.x + dx! * 18, y: at.y + dy! * 18 } });
  await expect.poll(selection).toEqual([]);
});

// ADR-116 decision 4: the nodes of a route put on the canvas from Find connections are marked with
// their degree from From, beside each node, wherever the layout put it.
test("a route's nodes are marked on the canvas with their degree from From", async ({ page }) => {
  await page.goto("/keyboard/harness.html?degrees=n0:0,n1:1,n2:2");
  const at = await layoutSettled(page, ["n0", "n2"]);
  const box = (await page.getByRole("application", { name: "Network canvas" }).boundingBox())!;
  const from = page.getByRole("img", { name: "From", exact: true });
  await expect(from).toHaveText("From");
  await expect(page.getByRole("img", { name: "1 degree from From" })).toHaveText("1°");
  const two = (await page.getByRole("img", { name: "2 degrees from From" }).boundingBox())!;
  // Beside n2, not somewhere else on the canvas.
  expect(Math.abs(two.x + two.width / 2 - (box.x + at.n2!.x))).toBeLessThan(40);
  expect(Math.abs(two.y - (box.y + at.n2!.y))).toBeLessThan(30);
});

// DESIGN.md v0.3 §9 exception 4 (ADR-115 decision 9): a 16px lattice, its lines border-subtle at 40%.
test("the canvas shows its 16px measurement grid behind the graph", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await page.waitForTimeout(600);
  const box = (await page.getByRole("application", { name: "Network canvas" }).boundingBox())!;
  const pixels = readPng(await page.screenshot());
  const scale = pixels.width / page.viewportSize()!.width;
  // A strip of empty canvas below the top-left controls: find a row inside the cells (the vertical
  // lines only), then the columns that differ from that row's commonest colour.
  const x0 = Math.round((box.x + 200) * scale);
  let found: number[] = [];
  for (let dy = 0; dy < 8 && found.length === 0; dy++) {
    const y = Math.round((box.y + 140 + dy) * scale);
    const row = Array.from({ length: Math.round(112 * scale) }, (_, i) => pixels.at(x0 + i, y));
    const key = (p: number[]) => p.slice(0, 3).join(",");
    const counts = new Map<string, number>();
    for (const p of row) counts.set(key(p), (counts.get(key(p)) ?? 0) + 1);
    const commonest = [...counts].sort((a, b) => b[1] - a[1])[0]![0];
    const lines = row.map((p, i) => (key(p) === commonest ? -1 : i)).filter((i) => i >= 0);
    if (lines.length >= 6 && lines.length <= 10) found = lines;
  }
  expect(found.length).toBeGreaterThanOrEqual(6);
  const gaps = found.slice(1).map((x, i) => (x - found[i]!) / scale);
  for (const gap of gaps) expect(gap).toBeCloseTo(16, 0);
});

test("the canvas's tools are one docked toolbar of labelled groups, with Show as one segmented control and no shadows", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/harness.html");
  const toolbar = page.getByRole("toolbar", { name: "Canvas tools" });
  await expect(toolbar).toBeVisible();
  for (const name of ["Select", "Layout", "Show", "View"]) {
    await expect(toolbar.getByRole("group", { name })).toBeVisible();
  }
  // One row at the canvas width a 1440px window gives (1440 less the 48px rail and the 340px right
  // panel, DESIGN.md §5a): the harness's own canvas is 900px; narrower than that the bar may wrap.
  await page.evaluate(() => { document.getElementById("root")!.style.width = "1052px"; });
  const show = toolbar.getByRole("group", { name: "Show" });
  await expect(show).toHaveClass(/segmented/);
  await expect(show.getByRole("button", { name: "Communities" })).toBeVisible();
  await expect(show.getByRole("button", { name: /^Labels/ })).toBeVisible();
  await expect(show.getByRole("button", { name: /^Icons/ })).toBeVisible();
  // One row: every group's top within a few pixels of the first's.
  const tops = await toolbar.getByRole("group").evaluateAll((els) => els.map((el) => el.getBoundingClientRect().top));
  for (const top of tops) expect(Math.abs(top - tops[0]!)).toBeLessThan(4);
  // Docked, so a hairline and no shadow (DESIGN.md §6), on the bar and every control in it. (A pressed
  // segment's underline is an inset stroke, not a shadow.)
  const shadows = await toolbar.evaluate((bar) =>
    [bar, ...Array.from(bar.querySelectorAll("button, select"))].map((el) => getComputedStyle(el).boxShadow),
  );
  expect(shadows.filter((s) => s !== "none" && !s.includes("inset"))).toEqual([]);
});

// ADR-115 E6 (the reference's toolbar, DESIGN.md §5a): the toolbar names the case's last change, and
// gives that room back below a 1100px window.
test("the toolbar's last change shows at desktop width and is hidden below 1100px", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/harness.html?last-change=" + encodeURIComponent("Last change: Expanded n0 by one hop, yesterday"));
  const note = page.getByRole("toolbar", { name: "Canvas tools" }).getByText("Last change: Expanded n0 by one hop, yesterday");
  await expect(note).toBeVisible();
  await page.setViewportSize({ width: 1000, height: 900 });
  await expect(note).toBeHidden();
});
