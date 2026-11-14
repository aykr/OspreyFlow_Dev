// Captures, not a test: Admin's People in the GOV.UK look at 1280px, for the pass's before and after
// (the owner's screenshot, 14 Nov). Written to ADMIN_LOOK_CAPTURE_DIR as <stage>-<state>.png.
import { test } from "@playwright/test";

const DIR = process.env.ADMIN_LOOK_CAPTURE_DIR ?? "";
const STAGE = process.env.ADMIN_LOOK_STAGE ?? "before";
const STATES = [
  ["people", "rights=manage_people&serve=people&brand=govuk"],
  ["people-all-rights", "rights=manage_people,manage_dashboards,operate_schedules,administer_system,manage_ontology,read_audit&serve=people&brand=govuk"],
] as const;

for (const [name, query] of STATES) {
  test(`capture ${name}`, async ({ page }) => {
    test.skip(!DIR, "ADMIN_LOOK_CAPTURE_DIR not set");
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`/keyboard/admin-harness.html?${query}`);
    await page.getByRole("table").first().waitFor();
    await page.screenshot({ path: `${DIR}/${STAGE}-${name}.png`, fullPage: true });
  });
}
