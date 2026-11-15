// Admin's words in the page's own face (v0.6.0 #6; the owner's ruling after AD, 15 November 2026). A role's label,
// a custom role's name, a schedule's label, the tips' role labels and an organisation arrival's sign-in name are words
// to read, set in mono until now. Mono stays for a value to copy (tokens.css: "every identifier … is set in mono.
// Mono means: this is a value you can copy"; DESIGN.md §9 exception 3). Measured by computed face, in the dark, light
// and GOV.UK looks.
import { expect, test, type Page } from "@playwright/test";

const LOOKS = [["dark", ""], ["light", ""], ["govuk", "&brand=govuk"]] as const;

async function faces(page: Page, texts: string[]) {
  return page.evaluate((texts) => {
    const first = (family: string) => family.split(",")[0]!.trim().replace(/["']/g, "").toLowerCase();
    const root = getComputedStyle(document.documentElement);
    const face = (text: string) => {
      const el = [...document.querySelectorAll(".admin-place *")].find(
        (e) => [...e.childNodes].some((n) => n.nodeType === 3 && (n.textContent ?? "").trim() === text));
      return el ? first(getComputedStyle(el).fontFamily) : `no element says ${text}`;
    };
    return { ui: first(root.getPropertyValue("--ui")), found: Object.fromEntries(texts.map((t) => [t, face(t)])) };
  }, texts);
}

const PAGES = [
  // People and roles: the tips' role labels and "Levels in a case", and a refused organisation sign-in's name.
  { name: "People and roles", query: "rights=manage_people&serve=people&arrivals=1", ready: "pat.example",
    open: "What each role and level lets a person do", texts: ["Analyst", "Levels in a case", "pat.example"] },
  // Roles: a built-in role's label and a custom role's name.
  { name: "Roles", query: "rights=manage_people&serve=people&open=Roles", ready: "Intel desk", texts: ["Super user", "Intel desk"] },
  // Operations: a schedule's label.
  { name: "Operations", query: "rights=operate_schedules&serve=operations&open=Operations", ready: "Daily custody export",
    texts: ["Daily custody export"] },
];  // prettier-ignore

for (const [look, brand] of LOOKS) {
  for (const p of PAGES) {
    test(`${p.name} in the ${look} look sets its words in the page's face`, async ({ page }) => {
      await page.goto(`/keyboard/admin-harness.html?${p.query}${brand}`);
      if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
      await page.getByText(p.ready, { exact: true }).first().waitFor();
      if ("open" in p && p.open) await page.getByText(p.open, { exact: true }).click(); // the tips' <details>
      await page.evaluate(() => document.fonts.ready.then(() => undefined));
      const m = await faces(page, p.texts);
      expect(m.found, "each word in the page's face").toEqual(Object.fromEntries(p.texts.map((t) => [t, m.ui])));
    });
  }
}
