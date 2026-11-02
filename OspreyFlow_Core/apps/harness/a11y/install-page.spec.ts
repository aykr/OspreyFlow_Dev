// The guided install page (`harness/install_page.py`, ADR-114 Amendment 3 decision 6), scanned by
// axe-core: the GDS re-audit, build-order step 9b (2 November 2026). Until this file the page had a
// keyboard walkthrough (`keyboard/setup-screens.spec.ts`) but no automated accessibility scan at all;
// `a11y.spec.ts` beside it scans the Set-up console's six screens, a different page.
//
// Every screen Lite's navigation offers is scanned in both themes, and the Mode screen twice more:
// with a starter chosen (ADR-138 decision 1) and with a GOV.UK starter, which draws the GOV.UK
// service's own fieldset (service name, organisation, phase). The screens are reached the way a
// person reaches them, by the page's own navigation buttons.
//
// The tags are WCAG 2.0, 2.1 and 2.2 at A and AA, as `apps/workspace/a11y/every-harness.spec.ts`
// uses: `wcag2a`/`wcag2aa` alone never run `target-size` (2.5.8) or `label-content-name-mismatch`
// (2.5.3). An automated scan finds only part of WCAG; a pass here is not a claim of conformance.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { INSTALL_BASE, INSTALL_TOKEN } from "./installPage";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

// Lite's screens (`src/store.ts`, `INSTALL_SCREENS.lite`), without Installing, which only an install
// draws.
const LITE_SCREENS = [
  "Mode",
  "Folders",
  "Profile",
  "Components",
  "Map",
  "Models",
  "Governance",
  "Demo packs",
  "Review",
] as const;

async function openInstallPage(page: Page, theme: "dark" | "light") {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page
    .context()
    .addCookies([{ name: "osprey_install", value: INSTALL_TOKEN, url: INSTALL_BASE }]);
  await page.goto(`${INSTALL_BASE}/keyboard/install-harness.html`);
  await page.getByRole("navigation", { name: "Install screens" }).waitFor();
  if (theme === "light") {
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  }
}

async function scan(page: Page) {
  await page.evaluate(() => document.fonts.ready);
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
}

for (const theme of ["dark", "light"] as const) {
  for (const screen of LITE_SCREENS) {
    test(`install page ${screen} screen (${theme}) has no automated WCAG 2.2 A or AA violations`, async ({
      page,
    }) => {
      await openInstallPage(page, theme);
      await page
        .getByRole("navigation", { name: "Install screens" })
        .getByRole("button", { name: screen, exact: true })
        .click();
      // The Map button opens the screen headed "Geospatial" (the Set-up console's own screen).
      const heading = screen === "Map" ? "Geospatial" : screen;
      await page.getByRole("heading", { name: heading, level: 2 }).waitFor();
      await scan(page);
    });
  }

  // ADR-138: the starter chosen but not saved, so nothing is written to the page's answers.
  for (const starter of ["ospreyflow-crime", "govuk-crime"] as const) {
    test(`install page Mode screen with the ${starter} starter (${theme}) has no automated WCAG 2.2 A or AA violations`, async ({
      page,
    }) => {
      await openInstallPage(page, theme);
      await page.getByRole("combobox", { name: "Starter (optional)" }).selectOption(starter);
      if (starter.startsWith("govuk")) {
        await expect(page.getByRole("textbox", { name: "Service name" })).toBeVisible();
      }
      await scan(page);
    });
  }
}
