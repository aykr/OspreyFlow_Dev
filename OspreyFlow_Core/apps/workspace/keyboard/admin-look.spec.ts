// Admin in each look (the owner's ruling, 14 November 2026: a font-sizing and usability pass on the GOV.UK
// look; the other two must not regress). Read from computed styles at 1280px on People and roles, the
// screen the owner's screenshot showed. GOV.UK: the Design System's scale (heading-l for the one h1, the
// "s" size, 16px, for the side navigation and the tables), names in the body face, every column header
// on one line, a person's rows at most 60% of their old height, "(coming)" items not links. The dark and
// light looks: the same structure, and the sizes main drew (measured on main 3c59060: nav and cells
// 13px, headers 12px and 67px tall, a row 122px tall). Their row grows by at most one line of actions
// (20px): the actions now sit beneath a person rather than beside them, which is what lets every column
// header keep to one line (each header at least 30px shorter than main's).
import { expect, test, type Page } from "@playwright/test";

const ALL_RIGHTS = "manage_people,manage_dashboards,operate_schedules,administer_system,manage_ontology,read_audit";
const LOOKS = [["dark", ""], ["light", ""], ["govuk", "&brand=govuk"]] as const;
//: What main drew (admin-look-measure, 14 Nov): the bound a look must not cross.
const MAIN = {
  dark: { nav: 13, cell: 13, header: 12, headerHeight: 67, row: 122 },
  light: { nav: 13, cell: 13, header: 12, headerHeight: 67, row: 122 },
  govuk: { nav: 19, cell: 19, header: 16, headerHeight: 113, row: 267 },
} as const;
//: One line of link-styled actions, beneath a person, in the dark and light looks.
const ACTION_LINE = 20;

async function open(page: Page, look: string, brand: string): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`/keyboard/admin-harness.html?rights=${ALL_RIGHTS}&serve=people${brand}`);
  if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  await page.getByRole("table").first().waitFor();
  // Measured before GDS Transport has loaded, a person's lines wrap in the fallback face (173px seen under a
  // parallel run, against 152px once loaded): wait for the faces, so the bound is the look's, not the race's.
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}

async function measure(page: Page) {
  return page.evaluate(() => {
    const px = (el: Element | null | undefined) => (el ? parseFloat(getComputedStyle(el).fontSize) : NaN);
    const place = document.querySelector(".admin-place")!;
    const table = place.querySelector(".admin-place__section table")!;
    const headers = [...table.querySelectorAll("thead th")].filter((th) => (th.textContent ?? "").trim());
    const row = table.querySelector("tbody tr")!;
    const name = row.querySelector("[data-person-name]");
    return {
      h1s: [...place.querySelectorAll("h1")].map((h) => ({ text: (h.textContent ?? "").trim(), size: px(h) })),
      caption: (place.querySelector(".admin-place__caption")?.textContent ?? "").trim(),
      nav: px(place.querySelector(".admin-nav__link")),
      cell: px(table.querySelector("tbody td")),
      header: px(headers[0]),
      headerHeight: Math.max(...headers.map((th) => th.getBoundingClientRect().height)),
      headerLines: headers.map((th) => {
        const lh = parseFloat(getComputedStyle(th).lineHeight);
        const pad = parseFloat(getComputedStyle(th).paddingTop) + parseFloat(getComputedStyle(th).paddingBottom);
        return Math.round((th.getBoundingClientRect().height - pad) / lh);
      }),
      // A person is their row and, since the GOV.UK pass, the row of actions beneath it.
      row: (() => {
        const actions = row.nextElementSibling?.classList.contains("admin-row-actions-row") ? row.nextElementSibling : row;
        return actions.getBoundingClientRect().bottom - row.getBoundingClientRect().top;
      })(),
      nameFont: name ? getComputedStyle(name).fontFamily : "no name element",
      comingLinks: [...place.querySelectorAll(".admin-nav a")].filter((a) => /coming/i.test(a.textContent ?? "")).length,
      comingTags: place.querySelectorAll(".admin-nav__coming").length,
      rolesLinkInTitleRow: !!place.querySelector(".admin-place__title-row a, .admin-place__title-row button"),
      primaryPerRow: (row.nextElementSibling ?? row).querySelectorAll(".admin-row-actions__primary").length
        + row.querySelectorAll(".admin-row-actions__primary").length,
    };
  });
}

for (const [look, brand] of LOOKS) {
  test(`Admin's People in the ${look} look: one h1, names in the body face, coming items not links`, async ({ page }) => {
    await open(page, look, brand);
    const m = await measure(page);
    expect(m.h1s.map((h) => h.text)).toEqual(["People and roles"]);
    expect(m.caption).toBe("Admin");
    expect(m.nameFont).not.toMatch(/mono/i);
    expect(m.comingLinks).toBe(0);
    expect(m.comingTags).toBeGreaterThan(0);
    expect(m.rolesLinkInTitleRow).toBe(true);
    expect(m.primaryPerRow).toBe(1);
    expect(m.headerLines.every((n) => n === 1)).toBe(true);
    expect(m.headerHeight).toBeLessThanOrEqual(MAIN[look].headerHeight - 30);
  });
}

test("Admin's People in the GOV.UK look: the Design System's scale, and a person at most 60% of their old height", async ({ page }) => {
  await open(page, "govuk", "&brand=govuk");
  const m = await measure(page);
  expect(m.h1s[0]?.size).toBe(36); // govuk-heading-l
  expect([m.nav, m.cell, m.header]).toEqual([16, 16, 16]); // the "s" size
  expect(m.row).toBeLessThanOrEqual(MAIN.govuk.row * 0.6);
});

for (const look of ["dark", "light"] as const) {
  test(`Admin's People in the ${look} look keeps main's sizes`, async ({ page }) => {
    await open(page, look, "");
    const m = await measure(page);
    expect([m.nav, m.cell, m.header]).toEqual([MAIN[look].nav, MAIN[look].cell, MAIN[look].header]);
    expect(m.row).toBeLessThanOrEqual(MAIN[look].row + ACTION_LINE);
  });
}
