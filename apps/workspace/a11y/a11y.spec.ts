// The accessibility floor — `docs/02_GLASS_FRONTEND.md` §6: "Contrast
// floor met in both themes; verify with automated checks in CI, not by
// eye." An automated, CI-gated pass/fail, not asserted in prose.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// `wcag2a` and `wcag2aa`, both — axe-core's own rule tags are not hierarchical: a rule tagged
// `wcag2a` (`button-name`, `image-alt`, ...) is not also returned by `wcag2aa` alone. Round 09:
// found still missing here — `apps/harness/a11y/a11y.spec.ts`'s own docstring had already
// disclosed this exact gap in this file without fixing it (a different surface, out of that
// round's scope); fixed now, on every scan below.
const WCAG_TAGS = ["wcag2a", "wcag2aa"];

for (const theme of ["dark", "light"] as const) {
  // `06_DECISIONS.md` ADR-050's own tests-owed list: "The accessibility floor
  // (`02_GLASS_FRONTEND.md` §6) on the sign-in screen." Against the real screen
  // (`keyboard/sign-in-harness.tsx` renders the actual `SignInScreen`, wired to the real
  // `signIn()` — nothing here needs the identity provider reachable, since axe scans the DOM
  // before the button is ever pressed), not a static showcase fragment, per ADR-050's own wording.
  test(`${theme} theme sign-in screen has no automated wcag2aa violations`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/keyboard/sign-in-harness.html");
    if (theme === "light") {
      await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
    }
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  // Round 09: the one real screen this file scanned for a general violation sweep was sign-in —
  // `keyboard/harness.html` (the real `GlassCanvas`, the same real screen `keyboard.spec.ts`
  // drives every one of its own real interaction tests against, never a showcase) had no a11y
  // coverage of its own at all. Scanned in its own initial, keyboard-focused state — the same
  // state `keyboard.spec.ts`'s own first test establishes before ever pressing a key.
  test(`${theme} theme canvas screen has no automated wcag2aa violations`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/keyboard/harness.html");
    if (theme === "light") {
      await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
    }
    await page.getByRole("application", { name: "Network canvas" }).waitFor();
    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

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
