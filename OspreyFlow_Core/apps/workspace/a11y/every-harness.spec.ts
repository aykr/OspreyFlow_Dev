// Every keyboard harness page, scanned by axe-core (the GDS baseline audit, build-order step 2b,
// 1 November 2026). `a11y.spec.ts` scans four real screens; the 38 harness pages under
// `keyboard/` each mount a real screen or panel, and before this file none but those four had an
// automated accessibility scan at all.
//
// The pages are discovered from the directory, never listed, so a new harness is scanned the day
// it is added (`CLAUDE.md` rule 13's lesson: a hard-coded walkthrough cannot see what it leaves
// out). Each is scanned in the dark and the light theme, and under the GOV.UK brand (ADR-132)
// wherever its harness applies the brand (`applyHarnessBrand`, read from the harness's own source;
// a harness that does not is a recorded gap in `process/gds/gds_remediation_plan.md`, not a pass).
//
// The tags are WCAG 2.0, 2.1 and 2.2 at A and AA: axe-core's tags are not hierarchical, and
// `a11y.spec.ts`'s `wcag2a`/`wcag2aa` alone never run `target-size` (2.5.8, WCAG 2.2) or
// `label-content-name-mismatch` (2.5.3, WCAG 2.1). Shown red first: the pipeline canvas's node
// buttons failed 2.5.3 before their names were taken from their visible text.
//
// An automated scan finds only part of WCAG; a pass here is not a claim of conformance.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readdirSync, readFileSync } from "node:fs";

const KEYBOARD = new URL("../keyboard/", import.meta.url);
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

// Elements a harness adds around the screen under test, never part of the product: each is a
// focus sentinel a keyboard spec tabs to, named here so that nothing else is excluded.
const HARNESS_ONLY: Record<string, string[]> = {
  "link-change-harness.html": ["#after-form"],
};

const pages = readdirSync(KEYBOARD).filter((name) => name.endsWith(".html")).sort();

function appliesBrand(page: string): boolean {
  const source = new URL(page.replace(/\.html$/, ".tsx"), KEYBOARD);
  try {
    return readFileSync(source, "utf8").includes("applyHarnessBrand");
  } catch {
    return false;
  }
}

test("the scan found the harness pages", () => {
  // A wrong directory would make every test below vanish rather than fail.
  expect(pages.length).toBeGreaterThan(30);
});

for (const name of pages) {
  const variants = ["dark", "light", ...(appliesBrand(name) ? ["govuk"] : [])] as const;
  for (const variant of variants) {
    test(`${name} (${variant}) has no automated WCAG 2.2 A or AA violations`, async ({ page }) => {
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.goto(`/keyboard/${name}${variant === "govuk" ? "?brand=govuk" : ""}`);
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => document.fonts.ready);
      if (variant === "light") {
        await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
      }
      if (variant === "govuk") {
        await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
      }
      let builder = new AxeBuilder({ page }).withTags(WCAG_TAGS);
      for (const selector of HARNESS_ONLY[name] ?? []) builder = builder.exclude(selector);
      const results = await builder.analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
    });
  }
}
