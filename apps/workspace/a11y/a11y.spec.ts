// The accessibility floor — `docs/02_GLASS_FRONTEND.md` §6: "Contrast
// floor met in both themes; verify with automated checks in CI, not by
// eye." An automated, CI-gated pass/fail, not asserted in prose.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const theme of ["dark", "light"] as const) {
  test(`${theme} theme has no automated colour-contrast violations`, async ({ page }) => {
    await page.goto("/a11y/showcase.html");
    if (theme === "light") {
      await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
    }
    const results = await new AxeBuilder({ page }).withTags(["wcag2aa"]).analyze();
    const contrastViolations = results.violations.filter((v) => v.id === "color-contrast");
    expect(
      contrastViolations,
      JSON.stringify(contrastViolations, null, 2),
    ).toEqual([]);
  });
}
