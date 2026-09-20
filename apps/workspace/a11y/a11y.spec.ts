// The accessibility floor — `docs/02_GLASS_FRONTEND.md` §6: "Contrast
// floor met in both themes; verify with automated checks in CI, not by
// eye." An automated, CI-gated pass/fail, not asserted in prose.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

for (const theme of ["dark", "light"] as const) {
  test(`${theme} theme has no automated colour-contrast violations`, async ({ page }) => {
    // Found while verifying Phase 7 Stage 5 (unrelated to it — this file was untouched): the
    // light-theme switch below flips `data-theme` on an already-painted page, and `.btn`'s own
    // `transition: background-color ...` (`design/primitives.css`) races it — axe-core can sample
    // mid-transition, an interpolated colour (e.g. `#a07323`, between dark `--brass:#c08a34` and
    // light `--brass:#8a6318`) that never actually rests there, an intermittent false positive on
    // `.btn--primary`'s real, passing light-theme contrast (5.42:1). `tokens.css` already zeroes
    // every transition under `prefers-reduced-motion: reduce` for exactly this class of "measure
    // the resting state, not a timing-dependent frame" concern — reused here rather than a bespoke
    // wait, which would only mask the race for this one element rather than for whatever the next
    // transitioning token turns out to be.
    await page.emulateMedia({ reducedMotion: "reduce" });
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
