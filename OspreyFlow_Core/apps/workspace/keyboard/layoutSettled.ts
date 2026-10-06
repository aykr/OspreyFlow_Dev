// Waits until the canvas's layout has stopped moving the given nodes. The layout runs 150ms after
// the last change and then animates for 420ms, so positions that hold for one short gap can be the
// quiet before it starts: link-selection.spec.ts aimed its clicks there and the nodes then moved
// away from them. Settled means unchanged across a whole second of reads.
import type { Page } from "@playwright/test";

const STEP_MS = 250;
const STEADY_READS = 4;

export async function layoutSettled(
  page: Page,
  ids: readonly string[],
): Promise<Record<string, { x: number; y: number }>> {
  const read = () =>
    page.evaluate(
      (nodes) =>
        Object.fromEntries(
          nodes.map((n) => [
            n,
            (window as unknown as {
              __CANVAS__?: { viewportPositionOf: (id: string) => { x: number; y: number } | null };
            }).__CANVAS__?.viewportPositionOf(n) ?? null,
          ]),
        ),
      [...ids],
    );
  let last = await read();
  let steady = 0;
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(STEP_MS);
    const now = await read();
    const complete = Object.values(now).every((p) => p !== null);
    steady = complete && JSON.stringify(now) === JSON.stringify(last) ? steady + 1 : 0;
    if (steady >= STEADY_READS) return now as Record<string, { x: number; y: number }>;
    last = now;
  }
  throw new Error("the layout never settled");
}
