// Admin in the page's own frame (the owner's screenshot of Admin › System, GOV.UK look, 15 November 2026). Two faults:
// the page scrolled in two places (Admin's place scrolled inside its own box while GOV.UK's footer stood after the
// frame, so the document scrolled too, and the side list and the page were cut at the footer's edge), and the System
// page's names were set in mono inside proportional sentences. Measured, never judged by eye, in the dark, light and
// GOV.UK looks:
// - one scroller holds Admin's section: the document, or a box of its own, never both;
// - under GOV.UK nothing of Admin's place is cut at the footer: it hides none of its content, and it ends above the
//   footer, which follows it;
// - each part of the System page is in the page's own face, but a model's id, a value to copy, stays in mono
//   (tokens.css: "every identifier … is set in mono. Mono means: this is a value you can copy").
import { expect, test, type Page } from "@playwright/test";

import { stripAtTheEnd } from "./stripInView";

const LOOKS = [["dark", ""], ["light", ""], ["govuk", "&brand=govuk"]] as const;

async function open(page: Page, look: string, brand: string): Promise<void> {
  // 700px tall, so the System page is taller than what the frame leaves it.
  await page.setViewportSize({ width: 1440, height: 700 });
  await page.goto(`/keyboard/admin-harness.html?frame=1&serve=system&rights=administer_system&open=System${brand}`);
  if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  await page.getByText("Case and rule stores (Postgres)").waitFor();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}

for (const [look, brand] of LOOKS) {
  test(`Admin in the page's frame in the ${look} look scrolls in one place, cut nowhere`, async ({ page }) => {
    await open(page, look, brand);
    const m = await page.evaluate(() => {
      const scrolls = (el: Element) => el.scrollHeight > el.clientHeight + 1;
      const section = document.querySelector(".admin-place__section")!;
      const boxes: string[] = [];
      for (let el: Element | null = section; el; el = el.parentElement) {
        if (el === document.documentElement || el === document.body) continue;
        if (/(auto|scroll)/.test(getComputedStyle(el).overflowY) && scrolls(el)) boxes.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]}`);
      }
      if (scrolls(document.scrollingElement!)) boxes.push("the document");
      const place = document.querySelector(".admin-place")!;
      const footer = document.querySelector(".govuk-footer");
      const y = (r: DOMRect, edge: "top" | "bottom") => r[edge] + window.scrollY;
      // Scrolled to the page's end, the side list is still in view (sticky) and ends above the footer.
      window.scrollTo(0, document.scrollingElement!.scrollHeight);
      const nav = document.querySelector(".admin-nav")!.getBoundingClientRect();
      return {
        boxes,
        navInView: Math.round(nav.top) >= 0,
        navAboveFooter: footer ? nav.bottom <= footer.getBoundingClientRect().top + 1 : true,
        hidden: place.scrollHeight - place.clientHeight,
        footerGap: footer ? Math.round(y(footer.getBoundingClientRect(), "top") - y(place.getBoundingClientRect(), "bottom")) : null,
      };
    });
    // Under GOV.UK the document is Admin's one scroller; in the standard look Admin's own box, as before.
    expect(m.boxes, "the one scroller").toEqual(look === "govuk" ? ["the document"] : ["section.admin-place"]);
    if (look === "govuk") {
      expect(m.hidden, "Admin's place hides none of its content").toBeLessThanOrEqual(1);
      expect(m.footerGap, "the footer follows Admin's place").toBeGreaterThanOrEqual(0);
      expect(m.navInView && m.navAboveFooter, "the side list stays in view, above the footer").toBe(true);
    }
  });

  test(`Admin › System in the ${look} look sets names in the page's face and a model's id in mono`, async ({ page }) => {
    await open(page, look, brand);
    const m = await page.evaluate(() => {
      const first = (family: string) => family.split(",")[0]!.trim().replace(/["']/g, "").toLowerCase();
      const root = getComputedStyle(document.documentElement);
      const ui = first(root.getPropertyValue("--ui"));
      const mono = first(root.getPropertyValue("--mono"));
      const face = (text: string) => {
        const el = [...document.querySelectorAll(".admin-place__section *")].find(
          (e) => [...e.childNodes].some((n) => n.nodeType === 3 && (n.textContent ?? "").trim() === text));
        return el ? first(getComputedStyle(el).fontFamily) : `no element says ${text}`;
      };
      return {
        ui, mono,
        names: ["Graph store", "Case and rule stores (Postgres)"].map(face),
        version: face("OspreyFlow v0.5.2"),
        marking: face("OFFICIAL-SENSITIVE"),
        converted: [...document.querySelectorAll(".admin-place__section p")]
          .filter((p) => /became (a view|views)/.test(p.textContent ?? ""))
          .map((p) => first(getComputedStyle(p).fontFamily)),
        model: face("gemini-2.5-flash"),
      };
    });
    expect(m.names, "the parts' names in the page's face").toEqual([m.ui, m.ui]);
    expect(m.version, "the version in the page's face").toBe(m.ui);
    expect(m.marking, "the marking ceiling in the page's face").toBe(m.ui);
    expect(m.converted.length, "the converted views are said").toBeGreaterThan(0);
    expect(m.converted, "the converted views in the page's face").toEqual(m.converted.map(() => m.ui));
    expect(m.model, "a model's id in mono, a value to copy").toBe(m.mono);
  });
}

// ADR-115 decision 2, the owner's ruling of 15 November 2026: the classification strip is always IN VIEW. Under GOV.UK,
// while Admin scrolls as a page, the strip stays pinned at the top of the window and nothing paints over it; the GOV.UK
// header and the top bar may scroll away. At 1440px and at 640px, scrolled to the footer.
for (const width of [1440, 640]) {
  test(`under GOV.UK at ${width}px, scrolled to the footer, Admin's classification strip stays at the window's top`, async ({ page }) => {
    await page.setViewportSize({ width, height: 700 });
    await page.goto("/keyboard/admin-harness.html?frame=1&serve=system&rights=administer_system&open=System&brand=govuk");
    await page.getByText("Case and rule stores (Postgres)").waitFor();
    const m = await stripAtTheEnd(page);
    expect(m.scrolled, "the page scrolled to the footer").toBe(true);
    expect(m.top, "the strip's top is the window's").toBe(0);
    expect(m.inside, "the strip is inside the window").toBe(true);
    expect(m.uncovered, "nothing paints over the strip").toEqual([true, true, true]);
  });
}
