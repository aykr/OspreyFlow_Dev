// L2.3 part 1 (ADR-145 decision 4): the case screen's lightening, as a prototype round for the owner.
// Counts each variant's controls by keyboard alone (rule 13: what a keyboard user passes through), and
// with `OSPREY_L23_SHOTS=<folder>` writes each variant's screenshot in the dark, light and GOV.UK
// themes there (the build tree's lane folder, `process/lanes/glass/l2.3/`). The harness is never wired
// into the app. The counts pinned below are the prototype's record, not the product's: its harness
// draws the mark without its Home button and stand-ins for the panels, so every count is one below the
// product's (`src/App.chrome.test.tsx` counts the real `App`) and the column's parts are a stand-in's
// (`keyboard/case-screen-parts.spec.ts` counts the real panels).
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";


/** Tab stops from the top of the page until the canvas has focus: the controls before the canvas. */
async function stopsBeforeCanvas(page: Page): Promise<string[]> {
  await page.locator("body").focus();
  const stops: string[] = [];
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press("Tab");
    const name = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (!el) return "";
      if (el.getAttribute("aria-label") === "Network canvas") return "CANVAS";
      return (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().replace(/\s+/g, " ");
    });
    if (name === "CANVAS") return stops;
    stops.push(name);
  }
  throw new Error("the canvas was never reached");
}

/** What the right-hand column shows open: each panel's parts visible to a reader. */
async function columnParts(page: Page): Promise<number> {
  return page.locator('aside[aria-label="Side panels"] .accordion-section button:visible').count();
}

// The skip link is the first stop on every page (ADR-132); it is the brand's, not the case screen's.
// Measured on 7 November 2026 at 1440 by 900; each count includes the skip link.
const EXPECTED: Record<string, { before: number; parts: number }> = {
  today: { before: 29, parts: 15 },
  a: { before: 29, parts: 8 },
  b: { before: 24, parts: 8 },
  c: { before: 20, parts: 8 },
};

for (const variant of Object.keys(EXPECTED)) {
  test(`${variant}: its controls before the canvas and the parts the column shows`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/case-screen-options-harness.html?variant=${variant}`);
    await expect(page.getByRole("application", { name: "Network canvas" })).toBeVisible();
    const stops = await stopsBeforeCanvas(page);
    console.log(`${variant}: ${stops.length} before the canvas: ${stops.join(" | ")}`);
    const parts = await columnParts(page);
    console.log(`${variant}: ${parts} parts shown in the right-hand column`);
    expect({ before: stops.length, parts }).toEqual(EXPECTED[variant]);
  });
}

test("the screenshots, in the dark, light and GOV.UK themes", async ({ page }) => {
  const shots = process.env.OSPREY_L23_SHOTS;
  test.skip(!shots, "set OSPREY_L23_SHOTS=<folder> to write them");
  mkdirSync(shots!, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const variant of Object.keys(EXPECTED)) {
    for (const theme of ["dark", "light", "govuk"] as const) {
      await page.goto(`/keyboard/case-screen-options-harness.html?variant=${variant}${theme === "govuk" ? "&brand=govuk" : ""}`);
      if (theme === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
      await expect(page.getByRole("application", { name: "Network canvas" })).toBeVisible();
      await page.screenshot({ path: `${shots}/${variant}-${theme}.png` });
    }
  }
});
