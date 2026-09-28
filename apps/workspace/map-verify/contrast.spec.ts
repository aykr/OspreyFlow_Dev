// The map's own contrast-floor Verify check — `spec/00_ARCHITECTURE.md`
// §1.2.1: "renders a fixture graph over it and compares against a stored
// reference for contrast floor compliance." Genuinely different from
// `a11y/a11y.spec.ts`'s axe-core DOM-rule check (component contrast, no
// map involved) — this is a rendered-pixel/reference-image comparison,
// via Playwright's own `toHaveScreenshot()`, against `showcase.tsx`'s
// static render of the basemap chrome + fixture graph node colours.
//
// Dark theme only — see `showcase.tsx`'s own docstring for why (the light
// MapLibre style doesn't exist yet).
//
// **Known gap, not silent**: this is the first pixel-comparison
// (`toHaveScreenshot`) test in the repo. Playwright names its baseline per
// OS (`map-contrast-dark-darwin.png`, generated on macOS here) — a CI
// runner on a different OS/font-rendering stack needs its own baseline
// regenerated there (`npx playwright test --config map-verify/
// playwright.config.ts --update-snapshots`), the same one-time step any
// new screenshot baseline needs on a new platform.
import { expect, test } from "@playwright/test";

test("the fixture graph over the basemap chrome meets the contrast floor", async ({ page }) => {
  await page.goto("/map-verify/showcase.html");
  await expect(page).toHaveScreenshot("map-contrast-dark.png", { maxDiffPixelRatio: 0.01 });
});
