// Inner scrollers stop at their own end (the owner's ruling, 15 November 2026, keeping ADR-132's frame): under GOV.UK the
// page scrolls to reach the footer, as any GOV.UK page does, and every box that scrolls inside it (a drawer's body,
// where Ask & Chat, Explore and History are drawn; the empty canvas's start overlay) stops at its own end. Wheeling past
// that end never moves the page, which once took the top bar off the top of the window. The standard look is
// unchanged: nothing there scrolls the page. Measured in `frame-harness`, the page as `main.tsx` and `App.tsx` draw it.
import { expect, test, type Page } from "@playwright/test";

const INNER = [
  ["a drawer's body", "drawer=1", ".drawer > .panel__body"],
  ["the empty canvas's start overlay", "overlay=1", ".explore-overlay"],
] as const;

async function wheelPastTheEnd(page: Page, selector: string) {
  const box = page.locator(selector).first();
  await box.waitFor();
  const at = (await box.boundingBox())!;
  await page.mouse.move(at.x + at.width / 2, at.y + Math.min(at.height / 2, 200));
  const before = await page.evaluate(() => window.scrollY);
  // To the box's own end, then on past it.
  for (let i = 0; i < 40; i++) await page.mouse.wheel(0, 400);
  await page.waitForTimeout(200);
  return page.evaluate(([sel, before]) => {
    const el = document.querySelector(sel as string)!;
    return { before: before as number, after: window.scrollY, atEnd: el.scrollTop + el.clientHeight >= el.scrollHeight - 1,
             scrolled: el.scrollTop > 0 };
  }, [selector, before] as const);
}

for (const [what, query, selector] of INNER) {
  test(`under GOV.UK, wheeling past ${what}'s end leaves the page where it was`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/frame-harness.html?${query}&brand=govuk`);
    // The page itself can scroll (the footer is below, ADR-132): what is held is that the box never moves it.
    expect(await page.evaluate(() => document.scrollingElement!.scrollHeight > document.scrollingElement!.clientHeight)).toBe(true);
    const m = await wheelPastTheEnd(page, selector);
    expect(m.scrolled && m.atEnd, `${what} itself scrolled to its end`).toBe(true);
    expect(m.after).toBe(m.before);
  });
}

test("in the standard look the page frame does not scroll the page at all, as before", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/frame-harness.html?drawer=1");
  await page.locator(".drawer > .panel__body").waitFor();
  expect(await page.evaluate(() => document.scrollingElement!.scrollHeight - document.scrollingElement!.clientHeight)).toBeLessThanOrEqual(0);
  const m = await wheelPastTheEnd(page, ".drawer > .panel__body");
  expect(m.atEnd && m.after === 0).toBe(true);
});
