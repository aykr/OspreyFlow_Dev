// Captures, not a test: Admin's People at 1280px in each look, for the pass's before and after (the owner's
// screenshot, 14 Nov). Written to ADMIN_LOOK_CAPTURE_DIR as <stage>-<state>.png. The viewport is tall enough
// for the whole section, since `.admin-place` scrolls inside the page and a full-page capture stops at it.
import { test } from "@playwright/test";

const DIR = process.env.ADMIN_LOOK_CAPTURE_DIR ?? "";
const STAGE = process.env.ADMIN_LOOK_STAGE ?? "before";
const ALL = "rights=manage_people,manage_dashboards,operate_schedules,administer_system,manage_ontology,read_audit&serve=people";
const STATES = [
  ["people", "rights=manage_people&serve=people&brand=govuk", ""],
  ["people-all-rights", `${ALL}&brand=govuk`, ""],
  ["people-all-rights-dark", ALL, ""],
  ["people-all-rights-light", ALL, "light"],
] as const;

for (const [name, query, theme] of STATES) {
  test(`capture ${name}`, async ({ page }) => {
    test.skip(!DIR, "ADMIN_LOOK_CAPTURE_DIR not set");
    await page.setViewportSize({ width: 1280, height: 1800 });
    await page.goto(`/keyboard/admin-harness.html?${query}`);
    if (theme) await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    await page.getByRole("table").first().waitFor();
    await page.evaluate(() => document.fonts.ready.then(() => undefined));
    await page.screenshot({ path: `${DIR}/${STAGE}-${name}.png`, fullPage: true });
  });
}
