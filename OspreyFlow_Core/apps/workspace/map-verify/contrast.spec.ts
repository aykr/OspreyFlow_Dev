// The map's own contrast-floor Verify check (`spec/00_ARCHITECTURE.md` §1.2.1: "renders a fixture
// graph over it and compares against a stored reference for contrast floor compliance"), in the
// dark, light and GOV.UK themes (P4). Different from `a11y/`'s axe scans, which see the page's DOM
// and not what the map paints: this measures the colours the map paints, read from their own call
// sites (`showcase.tsx`), against WCAG's floors (4.5:1 for text, 3:1 for a graphic's parts), and
// compares each theme's picture with its stored reference.
//
// Until P4 this ran in the dark theme only, because no light style existed; the bundled style has
// taken the theme's palette since 9 October 2026 (`map/style.ts`), so the light and GOV.UK themes
// were drawn and never checked.
//
// **Known gap, not silent**: Playwright names a baseline per OS (`map-contrast-dark-darwin.png`,
// generated on macOS here). A CI runner on another OS needs its own baselines made there once
// (`npx playwright test --config map-verify/playwright.config.ts --update-snapshots`). The measured
// floors below do not depend on the platform.
import { expect, test } from "@playwright/test";

const THEMES = [
  { name: "dark", query: "" },
  { name: "light", query: "?theme=light" },
  { name: "govuk", query: "?brand=govuk" },
] as const;

for (const theme of THEMES) {
  test(`the map's colours meet the contrast floor in the ${theme.name} theme`, async ({ page }) => {
    await page.goto(`/map-verify/showcase.html${theme.query}`);
    await expect.poll(() => page.evaluate(() => window.__CONTRAST__?.length ?? 0)).toBeGreaterThan(0);
    const pairs = (await page.evaluate(() => window.__CONTRAST__))!;
    expect(pairs.length).toBe(15);
    const under = pairs.filter((p) => p.ratio < p.floor);
    expect(under, JSON.stringify(under, null, 2)).toEqual([]);
    if (theme.name === "govuk") {
      await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
    }
    await expect(page.locator("html")).toHaveAttribute(
      "data-theme",
      theme.name === "dark" ? "dark" : "light",
    );
  });

  test(`the ${theme.name} theme's map matches its stored reference`, async ({ page }) => {
    await page.goto(`/map-verify/showcase.html${theme.query}`);
    await expect.poll(() => page.evaluate(() => window.__CONTRAST__?.length ?? 0)).toBeGreaterThan(0);
    await page.evaluate(() => document.fonts.ready);
    // A per-pixel threshold of 0.05, not the default 0.2: at 0.2 a dark scene's changes fall under
    // it, and the dark reference passed against a different picture altogether (P4_RED_RECORD.md).
    await expect(page).toHaveScreenshot(`map-contrast-${theme.name}.png`, {
      maxDiffPixelRatio: 0.01,
      threshold: 0.05,
    });
  });
}
