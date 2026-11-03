// Build order step 18c (the 3 November rehearsal's D3): with the weekend chosen, the weekly grid was
// drawn washed out in a checkerboard (Sunday pale, Thursday and Saturday dark at odd hours) though the
// counts were right. The option is replaced on a chart that already drew the grid, and the axes'
// stripes (`splitArea`) were then painted over the heat map. A drawing, not a keyboard action: it is
// here because this suite is the one that runs the real chart in a browser.
import { expect, test } from "@playwright/test";

type Drawn = { before: number[][]; after: number[][] };

for (const [name, query] of [
  ["choosing the weekend", "?cells"],
  ["drawing the grid again", ""],
] as const) {
  test(`${name} leaves every cell in the shade its count gives it (D3)`, async ({ page }) => {
    await page.goto(`/keyboard/cyclical-grid-harness.html${query}`);
    await page.waitForFunction(() => "gridColours" in window);
    const drawn = (await page.evaluate(() => (window as unknown as { gridColours: Drawn }).gridColours)) as Drawn;
    expect(drawn.before).toHaveLength(168);
    const changed = drawn.before
      .map((was, i) => ({ i, was, now: drawn.after[i]! }))
      .filter(({ was, now }) => was.some((v, c) => Math.abs(v - now[c]!) > 4));
    expect(changed.map(({ i, was, now }) => `${i % 24}h day ${Math.floor(i / 24)}: ${was} -> ${now}`)).toEqual([]);
  });
}
