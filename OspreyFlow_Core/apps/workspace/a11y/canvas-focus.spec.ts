// GDS remediation plan A2 (WCAG 4.1.3 Status Messages, 2.1.1 Keyboard): the canvas says which node
// keyboard focus is on. Beside the keyboard walkthrough's case (`keyboard/keyboard.spec.ts`), this
// reads the announcement as assistive technology meets it — a polite, atomic status region whose
// text is the node's name, type and links — and scans the page with axe in that state, so the
// region added for it brings no violation of its own.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("the focused node is announced in a polite status region, and the page passes axe", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/keyboard/harness.html");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await canvas.focus();
  await page.keyboard.press("ArrowRight");

  const region = page.getByRole("status").filter({ hasText: /^n1, Person, \d+ links?$/ });
  await expect(region).toHaveCount(1);
  await expect(region).toHaveAttribute("aria-live", "polite");
  await expect(region).toHaveAttribute("aria-atomic", "true");

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .exclude("#after-canvas")
    .analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});
