// What the canvas draws when the resolution slider moves (spec 02 §3, entity resolution). Nodes the
// engine has matched as one are drawn together at one place; when the match no longer holds (the
// slider moved to a stricter stop) each must go back to a place of its own, and when it holds again
// they come together again. The Fixture Corp walkthrough (steps 2.4 to 2.7) found the nodes staying
// stacked after a split, so a view at Balanced showed fewer people than it had before Strict.
// The harness's `?fixture=same-as` has three people in one cluster, `s0` (and `p0`, alone).
import { expect, test, type Page } from "@playwright/test";

declare global {
  interface Window {
    __CANVAS__?: {
      viewportPositionOf: (nodeId: string) => { x: number; y: number } | null;
      reproject: (clusterIds: Record<string, string>) => void;
    };
  }
}

const FIXTURE = "/keyboard/harness.html?fixture=same-as";

const at = (page: Page, id: string) => page.evaluate((n) => window.__CANVAS__?.viewportPositionOf(n), id);
const apart = (a: { x: number; y: number } | null | undefined, b: { x: number; y: number } | null | undefined) =>
  !!a && !!b && Math.hypot(a.x - b.x, a.y - b.y) > 8;

test("people matched as one are drawn together; a split puts each back in a place of its own", async ({ page }) => {
  await page.goto(FIXTURE);
  // At the threshold the page opens on, s0, s1 and s2 are one cluster, so one place.
  await expect.poll(async () => !apart(await at(page, "s0"), await at(page, "s1"))).toBe(true);
  await expect.poll(async () => !apart(await at(page, "s0"), await at(page, "s2"))).toBe(true);

  // Strict: the server sends a `reproject` delta and the three people are three clusters.
  await page.evaluate(() => window.__CANVAS__!.reproject({ s0: "s0", s1: "s1", s2: "s2" }));
  await expect.poll(async () => apart(await at(page, "s0"), await at(page, "s1"))).toBe(true);
  await expect.poll(async () => apart(await at(page, "s1"), await at(page, "s2"))).toBe(true);
  await expect.poll(async () => apart(await at(page, "s0"), await at(page, "s2"))).toBe(true);

  // Back to the first stop: matched again, one place again.
  await page.evaluate(() => window.__CANVAS__!.reproject({ s1: "s0", s2: "s0" }));
  await expect.poll(async () => !apart(await at(page, "s0"), await at(page, "s1"))).toBe(true);
  await expect.poll(async () => !apart(await at(page, "s0"), await at(page, "s2"))).toBe(true);
});
