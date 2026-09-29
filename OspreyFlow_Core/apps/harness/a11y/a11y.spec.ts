// The accessibility floor — `spec/02_GLASS_FRONTEND.md` §6, amendment 24 / ruling 6 (Stage 2 §6
// part C). `apps/workspace/a11y/a11y.spec.ts` is the precedent for the axe-core mechanics — a
// separate spec, not an extension of `keyboard/setup-screens.spec.ts` — but NOT for its own
// navigation: that file still loads `/a11y/showcase.html`, a static fragment, which
// `07_BUILD_PLAN.md`'s own Stage 6 finding already names as the gap ("real screens" scanned late,
// after the showcase had drifted from them). This file loads the real `App` from
// `apps/harness/src` — `/keyboard/setup-harness.html`, the same page `keyboard/setup-screens.
// spec.ts` already drives — wired to the real `harness.webapp` API this directory's own
// `playwright.config.ts` starts, and switches screens the same keyboard-only way that file does.
//
// **§6's own canvas-specific bullet ("Tab and Shift+Tab move focus in and out of the canvas...a
// container that captures every Tab keydown traps a keyboard user") does not apply here — there
// is no canvas anywhere in `apps/harness`.** "No focus trap" for these six screens is what
// `keyboard/setup-screens.spec.ts`'s own eleven real Tab-walkthroughs already prove every time Tab
// correctly reaches a screen's last field and Enter saves it, rather than getting stuck — not
// re-tested here a second way. `prefers-reduced-motion` is emulated below the same way the
// precedent's own contrast test already found necessary (a real transition-timing race on
// `.btn--primary`, not a hypothetical), and `spec/design/tokens.css`'s own focus-outline token
// (2px brass at 2px offset) is shared, unmodified, verbatim, with `apps/workspace` — no
// harness-specific CSS anywhere overrides it (checked directly: `apps/harness/src/app.css` sets no
// `outline` property at all).
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SCREENS = [
  "Profile",
  "Components",
  "Models",
  "Governance",
  "Geospatial",
  "Preflight",
] as const;

for (const theme of ["dark", "light"] as const) {
  for (const screen of SCREENS) {
    test(`${theme} theme ${screen} screen has no automated wcag2aa violations`, async ({
      page,
    }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto("/keyboard/setup-harness.html");
      if (theme === "light") {
        await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
      }
      if (screen !== "Profile") {
        await page.getByRole("button", { name: screen, exact: true }).focus();
        await page.keyboard.press("Enter");
      }
      // The screen's own `<h2>` — waited for so axe scans the screen actually switched to, not a
      // stale previous one mid-transition.
      await page.getByRole("heading", { name: screen, level: 2 }).waitFor();

      // `wcag2a` and `wcag2aa`, both — axe-core's own rule tags are not hierarchical: a rule
      // tagged `wcag2a` (e.g. `button-name`, `image-alt`) is not also returned by `wcag2aa` alone,
      // confirmed directly building this file's own red-then-green proof (a planted unlabelled
      // button passed silently under `wcag2aa` alone). `apps/workspace/a11y/a11y.spec.ts`'s own
      // `withTags(["wcag2aa"])` carries the identical gap — recorded in `07_BUILD_PLAN.md` as a
      // real, disclosed finding, not fixed here (a different surface, out of this round's scope).
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
    });
  }
}
