// The Glass page's panels and menus on the page's own type scale, in every look (the owner's exception, v0.5.2,
// 14 November 2026). The workspace keeps its 13px base under GOV.UK too (DESIGN.md §9 exception 1; tokens.css
// remaps GOV.UK's scale only for the welcome, home and Admin pages). But a panel that switches to GOV.UK Frontend's
// classes under GOV.UK brought that system's own sizes in: the saved views panel's names at 19px bold, its tags at
// 19px, its links at 16px, beside a 13px page. Measured, never judged by eye: each panel's and menu's text against the
// page's scale, read from the page's own tokens where the panel sits. Text is at --fs-11, --fs-12 or --fs-13 (the
// small meta, the small text, the body); a heading or a panel's title at --fs-12, --fs-13 or --fs-16.
import { expect, test, type Page } from "@playwright/test";

const LOOKS = [["dark", ""], ["light", ""], ["govuk", "brand=govuk"]] as const;

/** Each panel or menu: where it is drawn, how it is opened, and the container its text is measured in. */
const PANELS: { name: string; harness: string; query: string; open?: (page: Page) => Promise<void>; within: string;
                width?: number }[] = [
  // The right-hand panel: the case's saved views in the Cases drawer (the owner's screenshot).
  { name: "the saved views panel, in its drawer", harness: "views-harness", query: "in=drawer", within: ".drawer" },
  // The strip over the canvas while a saved view is open.
  { name: "the open view's strip over the canvas", harness: "views-harness", query: "show=lens", within: ".view-lens-banner" },
  // More's menu (once More views), by either of its names.
  { name: "the top bar's More menu", harness: "top-bar-harness", query: "",
    open: async (page) => {
      await page.getByRole("button", { name: /^(More views|More ways to show the case)/ }).click();
    },
    within: ".menu-panel" },
  // More's menu at a narrow width, holding everything the bar folds into it, Build a report among them (a GOV.UK link
  // out of the Glass, the "panel that opens from More" the owner saw).
  { name: "the top bar's More menu, folded narrow, with Build a report", harness: "top-bar-harness", query: "reports=1",
    width: 760,
    open: async (page) => {
      // At this width everything folds into the open view's own button (Graph ▾), whose menu is More's.
      await page.getByRole("button", { name: /^(More views|More ways to show the case|More|Graph)\b/ }).first().click();
    },
    within: ".menu-panel" },
  // The case line's menu: the case switcher.
  { name: "the case switcher's menu", harness: "top-bar-harness", query: "",
    open: async (page) => {
      await page.getByRole("button", { name: /^Case:/ }).first().click();
    },
    within: ".menu-panel" },
  // The drawer frame and the case line beside it.
  { name: "a drawer and the case line", harness: "shell-harness", query: "drawer=1", within: ".drawer, .context-banner" },
];  // prettier-ignore

async function measure(page: Page, within: string) {
  return page.evaluate((within) => {
    const px = (v: string) => parseFloat(v);
    // Drawn: a fixed drawer has no offsetParent, so the boxes it occupies are what say it is shown.
    const drawn = (el: Element) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
    const containers = [...document.querySelectorAll(within)].filter(drawn);
    const found: { text: string; size: number; heading: boolean; allowed: number[] }[] = [];
    for (const box of containers) {
      const scale = (n: number) => px(getComputedStyle(box).getPropertyValue(`--fs-${n}`));
      const text = [scale(11), scale(12), scale(13)];
      const heading = [scale(12), scale(13), scale(16)];
      for (const el of box.querySelectorAll("*")) {
        const own = [...el.childNodes].filter((n) => n.nodeType === 3 && (n.textContent ?? "").trim()).map((n) => n.textContent!.trim()).join(" ");
        if (!own) continue;
        const cs = getComputedStyle(el);
        if (!drawn(el) || el.closest(".visually-hidden, .govuk-visually-hidden")) continue;
        const isHeading = /^H[1-6]$/.test(el.tagName) || el.matches(".panel__title, [class*='govuk-heading']");
        found.push({ text: own.slice(0, 50), size: px(cs.fontSize), heading: isHeading, allowed: isHeading ? heading : text });
      }
    }
    return { containers: containers.length, found };
  }, within);
}

for (const [look, brand] of LOOKS) {
  for (const p of PANELS) {
    test(`${p.name} in the ${look} look is on the page's type scale`, async ({ page }) => {
      await page.setViewportSize({ width: p.width ?? 1280, height: 900 });
      await page.goto(`/keyboard/${p.harness}.html?${[p.query, brand].filter(Boolean).join("&")}`);
      if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
      if (p.open) await p.open(page);
      else await page.locator(p.within.split(",")[0]!).first().waitFor();
      await page.evaluate(() => document.fonts.ready.then(() => undefined));
      await expect.poll(async () => (await measure(page, p.within)).found.length).toBeGreaterThan(2);
      const m = await measure(page, p.within);
      const off = m.found.filter((f) => !f.allowed.includes(f.size)).map((f) => `${f.size}px${f.heading ? " (heading)" : ""}: ${f.text}`);
      expect(off).toEqual([]);
    });
  }
}
