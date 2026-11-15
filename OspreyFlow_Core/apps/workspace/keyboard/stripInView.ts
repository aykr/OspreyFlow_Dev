// ADR-115 decision 2 (the owner's ruling of 15 November 2026): the classification strip is always in view. Shared by
// `admin-frame.spec.ts` and `frame-scroll.spec.ts`.
import type { Page } from "@playwright/test";

/** Scrolled to the page's end: where the strip is, and whether the strip itself is what is drawn at three of its points (its left end, under Admin's side list; its middle;
 * its right end, under a drawer). */
export async function stripAtTheEnd(page: Page) {
  return page.evaluate(() => {
    window.scrollTo(0, document.scrollingElement!.scrollHeight);
    const strip = document.querySelector(".classification-strip")!;
    const r = strip.getBoundingClientRect();
    const y = r.top + r.height / 2;
    const at = (x: number) => { const hit = document.elementFromPoint(x, y); return !!hit && strip.contains(hit); };
    return { scrolled: window.scrollY > 0, top: Math.round(r.top), inside: r.top >= 0 && r.bottom <= window.innerHeight && r.height > 0,
             uncovered: [at(r.left + 40), at(r.left + r.width / 2), at(r.right - 8)] };
  });
}
