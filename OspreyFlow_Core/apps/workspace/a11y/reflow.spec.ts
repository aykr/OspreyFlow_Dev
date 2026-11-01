// WCAG 2.2 1.4.10 Reflow (AA): at 320 CSS pixels wide a page's content reads without scrolling
// sideways (the GDS baseline audit, build-order step 2b, 1 November 2026). Only the page-shaped
// screens are held to it here. The graph canvas, the map and the timeline are two-dimensional
// content, which 1.4.10 exempts; the audit records how each is reached instead
// (`process/gds/gds_compliance_report.md`).
//
// Shown red first: the start page's two columns had a 340px minimum (`home.css`'s
// `.home-columns`), 35px wider than a 320px viewport, under both brands.
import { expect, test } from "@playwright/test";

const PAGES = [
  ["start page", "/keyboard/start-harness.html"],
  ["start page (GOV.UK)", "/keyboard/start-harness.html?brand=govuk"],
  ["sign-in page", "/keyboard/sign-in-harness.html"],
  ["sign-in page (GOV.UK)", "/keyboard/sign-in-harness.html?brand=govuk"],
  ["shell (GOV.UK)", "/keyboard/shell-harness.html?brand=govuk"],
] as const;

test.use({ viewport: { width: 320, height: 640 } });

for (const [name, url] of PAGES) {
  test(`the ${name} reflows at 320px with no sideways scroll`, async ({ page }) => {
    await page.goto(url);
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => document.fonts.ready);
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth, `${name}: ${scrollWidth}px of content in a ${clientWidth}px viewport`).toBeLessThanOrEqual(
      clientWidth,
    );
  });
}
