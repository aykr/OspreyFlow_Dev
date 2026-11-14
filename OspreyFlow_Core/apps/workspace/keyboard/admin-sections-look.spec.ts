// Admin's other sections' headings, in each look (ADR-145 Amendment 16, the orchestrator's follow-up of 14 November
// 2026): as People's, each section's own headings step down from its one h1 without skipping a level, each drawn
// smaller than the h1; and in GOV.UK a person's row links take GOV.UK's link focus (`govuk-link`). Models and Maps
// are the platform lane's (admin-look.spec.ts).
import { expect, test, type Page } from "@playwright/test";

const ALL = "manage_people,manage_dashboards,operate_schedules,administer_system,manage_ontology,read_audit";
const LOOKS = [["dark", ""], ["light", ""], ["govuk", "&brand=govuk"]] as const;
//: Each section, the harness state that draws its own headings, a heading that must be drawn there, and a button
//: pressed first to draw it, if any.
const SECTIONS = [
  ["Roles", "serve=people&open=Roles", "New role", "New role"],
  ["Dashboard identities", "serve=packs&open=Dashboard%20identities", "Register a dashboard", ""],
  ["Datasets", "serve=datasets&open=Datasets&show=details", "Authors", ""],
  ["System", "serve=datasets&open=System", "Dataset owners", ""],
  ["Operations", "serve=operations&open=Operations", "Promotions waiting for review", ""],
  ["Demo packs", "serve=packs&open=Demo%20packs", "Fixture pack A (synthetic)", ""],
] as const;

async function open(page: Page, look: string, query: string): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`/keyboard/admin-harness.html?rights=${ALL}&${query}`);
  if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}

for (const [look, brand] of LOOKS) {
  for (const [section, query, drawn, press] of SECTIONS) {
    test(`${section} in the ${look} look: one h1, no level skipped beneath it, each below the h1`, async ({ page }) => {
      await open(page, look, `${query}${brand}`);
      const region = page.getByRole("region", { name: section });
      if (press) await region.getByRole("button", { name: press, exact: true }).click();
      await expect(region.getByRole("heading", { name: drawn, exact: true })).toBeVisible();
      const headings = await region.evaluate((el) => {
        const px = (h: Element) => parseFloat(getComputedStyle(h).fontSize);
        return [...el.querySelectorAll("h1, h2, h3, h4, h5, h6")].map((h) => ({
          level: Number(h.tagName[1]), text: (h.textContent ?? "").trim(), size: px(h) }));  // prettier-ignore
      });
      expect(headings.filter((h) => h.level === 1).map((h) => h.text)).toEqual([section]);
      const skips = headings.slice(1).filter((h, i) => h.level > headings[i].level + 1).map((h) => `${h.text} h${h.level}`);
      expect(skips).toEqual([]);
      const h1 = headings[0].size;
      expect(headings.slice(1).filter((h) => h.size >= h1).map((h) => `${h.text} ${h.size}px`)).toEqual([]);
    });
  }
}

test("a person's row links take GOV.UK's link focus in the GOV.UK look", async ({ page }) => {
  await open(page, "govuk", "serve=people&brand=govuk");
  const link = page.getByRole("button", { name: /^Super user preset for / }).first();
  await link.focus();
  const drawn = await link.evaluate((el) => {
    const cs = getComputedStyle(el);
    return { classes: [...el.classList], background: cs.backgroundColor, shadow: cs.boxShadow };
  });
  expect(drawn.classes).toContain("govuk-link");
  expect(drawn.background).toBe("rgb(255, 221, 0)"); // GOV.UK's focus yellow
  expect(drawn.shadow).toContain("rgb(11, 12, 12)"); // and its black underline bar
});
