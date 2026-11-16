// The Glass page's panels and menus on the page's own type scale, in every look (the owner's exception, v0.5.2,
// 14 November 2026; spec/design/DESIGN.md §11). The workspace keeps its 13px base under GOV.UK too (DESIGN.md §9
// exception 1; tokens.css remaps GOV.UK's scale only for the welcome, home and Admin pages). Two things broke it under
// GOV.UK: a panel drawn with GOV.UK Frontend's classes took the Design System's sizes (the saved views panel's names
// at 19px bold, its tags at 19px, its links at 16px), and a menu that sets no size inherited the case line's 19px
// GOV.UK banner. Measured, never judged by eye: each panel's and menu's text against the page's scale, read from the
// page (its body), not from the panel, so a panel given another scale could not pass by redefining its own tokens.
// Text is at --fs-12 or --fs-13 (small text, body); a tag, meta or caption may also be --fs-11 (dense meta); a
// heading or a panel's title at --fs-12, --fs-13 or --fs-16.
import { expect, test, type Page } from "@playwright/test";

const LOOKS = [["dark", ""], ["light", ""], ["govuk", "brand=govuk"]] as const;

interface Panel {
  name: string;
  harness: string;
  query: string;
  /** Opens the panel or menu; without one, the panel is drawn on load. */
  open?: (page: Page) => Promise<void>;
  /** Each selector must match at least one drawn container: one matching nothing is a failure, never a pass. */
  within: string[];
  /** What must be drawn, and so measured, before the measure: never the loading state alone. */
  ready?: string;
  /** Text that must be among what is measured. */
  holds?: string[];
  width?: number;
}

/** The menu button that opens what the bar folds: More (once More views), or at a narrow width the open view's own. */
const MORE = /^(More views|More ways to show the case|More)\b/;

const PANELS: Panel[] = [
  // The right-hand panel: the case's saved views in the Cases drawer (the owner's screenshot), once the views are read.
  { name: "the saved views panel, in its drawer", harness: "views-harness", query: "in=drawer", within: [".drawer"],
    ready: "[data-view-id]", holds: ["Private", "Shared"] },
  // The open saved view's *Details*, over the canvas from the case line (ADR-145 Amendment 19; the strip withdrawn).
  { name: "the open saved view's Details, over the canvas", harness: "views-harness", query: "show=lens&details=open", within: [".case-line-details"],
    holds: ["Nothing in a saved view changes the case."] },
  // The Save as a view form, over the canvas.
  { name: "the Save as a view form", harness: "views-harness", query: "show=form", within: [".save-view"] },
  // More's menu, in the page's own frame (the brand frame, the case line), as the Glass draws it.
  { name: "the top bar's More menu, in the Glass's frame", harness: "places-harness", query: "place=glass",
    open: async (page) => { await page.getByRole("button", { name: MORE }).first().click(); }, within: [".menu-panel"] },
  // More's menu at a narrow width, holding everything the bar folds into it, Build a report among them.
  { name: "the top bar's More menu, folded narrow, with Build a report", harness: "top-bar-harness", query: "reports=1",
    width: 760,
    // The menu button's ▾ is in its text, not its name; at this width Graph is the open view's own menu button.
    open: async (page) => { await page.getByRole("button").filter({ hasText: /^(More|Graph)[^▾]*▾/ }).first().click(); },
    within: [".menu-panel"], holds: ["Build a report"] },
  // The case line's menu: the case switcher, inside the case line (a 19px GOV.UK banner under that brand).
  { name: "the case line's case switcher", harness: "places-harness", query: "place=glass",
    open: async (page) => { await page.getByRole("button", { name: /^Case:/ }).first().click(); }, within: [".menu-panel"] },
  // ...and its New case form, which draws a label and options with no size of their own.
  { name: "the case line's New case form", harness: "places-harness", query: "place=glass",
    open: async (page) => {
      await page.getByRole("button", { name: /^Case:/ }).first().click();
      await page.getByRole("button", { name: "New case" }).click();
    },
    within: [".menu-panel"], holds: ["What data does this case read?"] },
  // Two of the Glass's drawers: Explore, and Export.
  { name: "the Explore drawer", harness: "explore-harness", query: "", within: [".drawer"] },
  { name: "the Export drawer", harness: "export-panel-harness", query: "", within: [".drawer"] },
];  // prettier-ignore

async function measure(page: Page, within: string[]) {
  return page.evaluate((within) => {
    const px = (v: string) => parseFloat(v);
    // Drawn: a fixed drawer has no offsetParent, so the boxes it occupies are what say it is shown.
    const drawn = (el: Element) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
    // The page's scale, from the page itself.
    const page = getComputedStyle(document.body);
    const scale = (n: number) => px(page.getPropertyValue(`--fs-${n}`));
    const text = [scale(12), scale(13)];
    const meta = [scale(11), scale(12), scale(13)];
    const heading = [scale(12), scale(13), scale(16)];
    const unmatched = within.filter((sel) => ![...document.querySelectorAll(sel)].some(drawn));
    const found: { text: string; size: number; role: string; allowed: number[] }[] = [];
    for (const box of within.flatMap((sel) => [...document.querySelectorAll(sel)]).filter(drawn)) {
      for (const el of box.querySelectorAll("*")) {
        const own = [...el.childNodes].filter((n) => n.nodeType === 3 && (n.textContent ?? "").trim())
          .map((n) => n.textContent!.trim()).join(" ");
        if (!own || !drawn(el) || el.closest(".visually-hidden, .govuk-visually-hidden")) continue;
        const role = /^H[1-6]$/.test(el.tagName) || el.matches(".panel__title, [class*='govuk-heading']") ? "heading"
          : el.matches("[class*='tag'], [class*='meta'], .caption") ? "meta" : "text";
        found.push({ text: own.slice(0, 50), size: px(getComputedStyle(el).fontSize), role,
                     allowed: role === "heading" ? heading : role === "meta" ? meta : text });
      }
    }
    return { unmatched, found };
  }, within);
}

for (const [look, brand] of LOOKS) {
  for (const p of PANELS) {
    test(`${p.name} in the ${look} look is on the page's type scale`, async ({ page }) => {
      await page.setViewportSize({ width: p.width ?? 1280, height: 900 });
      await page.goto(`/keyboard/${p.harness}.html?${[p.query, brand].filter(Boolean).join("&")}`);
      if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
      if (p.open) await p.open(page);
      await page.locator(p.ready ?? p.within[0]!).first().waitFor();
      await page.evaluate(() => document.fonts.ready.then(() => undefined));
      const m = await measure(page, p.within);
      expect(m.unmatched, "a container the case names is drawn").toEqual([]);
      expect(m.found.length).toBeGreaterThan(2);
      for (const words of p.holds ?? []) expect(m.found.map((f) => f.text).join(" | ")).toContain(words);
      const off = m.found.filter((f) => !f.allowed.includes(f.size)).map((f) => `${f.size}px (${f.role}): ${f.text}`);
      expect(off).toEqual([]);
    });
  }
}
