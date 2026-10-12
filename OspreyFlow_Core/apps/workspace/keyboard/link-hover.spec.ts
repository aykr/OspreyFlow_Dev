// ADR-115 E5 (review item 11): hovering a link shows its type and how many links of that type join the
// same two entities, in a tooltip by the pointer, gone when the pointer leaves. A pointer behaviour,
// so this spec moves the mouse (as `node-drag.spec.ts` does); a keyboard user reads the same from the
// Inspector with the link selected.
import { expect, test, type Page } from "@playwright/test";

import { layoutSettled } from "./layoutSettled";

const at = (page: Page, id: string) => page.evaluate((n) => window.__CANVAS__?.viewportPositionOf(n) ?? null, id);

test("hovering a link names its type and count, and leaving it takes the tooltip away", async ({ page }) => {
  await page.goto("/keyboard/harness.html");
  await layoutSettled(page, ["n0", "n1"]);
  const box = (await page.getByRole("application", { name: "Network canvas" }).boundingBox())!;
  const a = (await at(page, "n0"))!;
  const b = (await at(page, "n1"))!;
  await page.mouse.move(box.x + (a.x + b.x) / 2, box.y + (a.y + b.y) / 2, { steps: 4 });
  const tooltip = page.getByRole("tooltip");
  await expect(tooltip).toContainText("Associate of");
  await expect(tooltip).toContainText("1 link of this type between these two");
  await page.mouse.move(box.x + 4, box.y + box.height - 4, { steps: 4 });
  await expect(page.getByRole("tooltip")).toHaveCount(0);
});
