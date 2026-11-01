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

// States a harness draws only when asked, scanned as well as its default. The start page as an
// analyst (no Studio or Admin right) draws those two panels gated: the live audit of 1 November 2026
// found their text at 4.25:1 there, which the default (an administrator, nothing gated) never drew.
const EXTRA_STATES: Record<string, string[]> = {
  "start-harness.html": ["rights=investigate"],
  // The Matrix view (GDS remediation plan A1) with rows selected, and long enough to page.
  "matrix-harness.html": ["select=p2,p4", "many=1"],
  // ADR-133 stage (b): the Rules tab with a rule written as a sentence, its drawn pattern and its
  // preview shown.
  // ADR-133 stage (c): the Lists tab, as a reader and as whoever may load lists after a refresh
  // (its refreshes, a failure in words, the subscribe form), and an AML template filling the form.
  "monitoring-harness.html": [
    "tab=rules&sentence=preview",
    "tab=lists",
    "tab=lists&lists=manage&refreshed=1",
    "tab=rules&template=high_risk_jurisdiction",
    // ADR-133 stage (d): a whole-deployment rule waiting for a second person (Approve and Reject
    // offered), a scheduled rule's runs and versions open, a sentence set to run every week, a
    // high-severity alert whose close waits for approval, and a list refreshed on a schedule with
    // its schedule form.
    "stage=d&tab=rules&opened=1",
    "stage=d&tab=rules&sentence=schedule",
    "stage=d&open=a-close",
    "stage=d&tab=lists&lists=manage",
  ],
  // ADR-133 decision 6, stage (d): the Checks on load step (the default) and Verify's would-be alerts.
  "checks-on-load-harness.html": ["view=verify"],
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
  for (const state of ["", ...(EXTRA_STATES[name] ?? [])]) {
    for (const variant of variants) {
      const query = [state, variant === "govuk" ? "brand=govuk" : ""].filter(Boolean).join("&");
      const title = `${name}${state ? ` ${state}` : ""} (${variant})`;
      test(`${title} has no automated WCAG 2.2 A or AA violations`, async ({ page }) => {
        await page.emulateMedia({ reducedMotion: "reduce" });
        await page.goto(`/keyboard/${name}${query ? `?${query}` : ""}`);
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
}
