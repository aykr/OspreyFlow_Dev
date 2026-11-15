// Inner scrollers never move the page under GOV.UK (the owner's ruling, 15 November 2026, keeping ADR-132's frame):
// under that brand the page scrolls to reach the footer, as any GOV.UK page does, and a wheel that starts in a box that
// scrolls (a drawer's body, where Explore and History are drawn; the empty canvas's start overlay) stops
// at that box's end and never moves the page, which once took the top bar off the top of the window
// (`src/brand/containInnerScroll.ts`). Nothing else changes: a box inside another still hands the wheel on when it is
// at its end (a short list to its drawer), a box that scrolls only sideways never swallows a vertical wheel, a wheel
// over a part of the page that does not scroll still scrolls the page to the footer, and the standard look has no
// footer and nothing that scrolls the page. Measured in `frame-harness`, the page as `main.tsx` and `App.tsx` draw it.
import { expect, test, type Page } from "@playwright/test";

import { stripAtTheEnd } from "./stripInView";

async function wheelOver(page: Page, selector: string, times = 40) {
  const at = (await page.locator(selector).first().boundingBox())!;
  await page.mouse.move(at.x + Math.min(at.width / 2, 200), at.y + Math.min(at.height / 2, 30));
  for (let i = 0; i < times; i++) await page.mouse.wheel(0, 400);
  await page.waitForTimeout(250);
}

const state = (page: Page, selector: string) =>
  page.evaluate((sel) => {
    const el = document.querySelector(sel)!;
    return { page: window.scrollY, top: el.scrollTop, atEnd: el.scrollTop + el.clientHeight >= el.scrollHeight - 1 };
  }, selector);

for (const [what, query, selector] of [
  ["a drawer's body", "drawer=1", ".drawer > .panel__body"],
  ["the empty canvas's start overlay", "overlay=1", ".explore-overlay"],
] as const) {
  test(`under GOV.UK, wheeling past ${what}'s end leaves the page where it was`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/frame-harness.html?${query}&brand=govuk`);
    await page.locator(selector).waitFor();
    // The page itself can scroll (the footer is below, ADR-132): what is held is that the box never moves it.
    expect(await page.evaluate(() => document.scrollingElement!.scrollHeight > document.scrollingElement!.clientHeight),
      "the page can scroll").toBe(true);
    await wheelOver(page, selector);
    const m = await state(page, selector);
    expect(m.top > 0 && m.atEnd, `${what} itself scrolled to its end`).toBe(true);
    expect(m.page, "the page did not move").toBe(0);
  });
}

for (const [look, brand] of [["dark", ""], ["govuk", "&brand=govuk"]] as const) {
  test(`in the ${look} look a vertical wheel over a sideways box moves the drawer around it`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/frame-harness.html?drawer=1${brand}`);
    await wheelOver(page, "[data-box='sideways']", 3);
    expect((await state(page, ".drawer > .panel__body")).top, "the drawer scrolled").toBeGreaterThan(0);
  });

  test(`in the ${look} look wheeling past a short list's end moves the drawer around it`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/keyboard/frame-harness.html?drawer=1${brand}`);
    await wheelOver(page, "[data-box='short-list']", 6);
    expect((await state(page, "[data-box='short-list']")).atEnd, "the list scrolled to its end").toBe(true);
    expect((await state(page, ".drawer > .panel__body")).top, "then the drawer scrolled").toBeGreaterThan(0);
  });
}

test("under GOV.UK a wheel over the top bar still scrolls the page to the footer", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/frame-harness.html?drawer=1&brand=govuk");
  await wheelOver(page, ".top-bar", 3);
  expect(await page.evaluate(() => window.scrollY), "the page scrolled").toBeGreaterThan(0);
});

test("in the standard look the page frame does not scroll the page at all, as before", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/frame-harness.html?drawer=1");
  await page.locator(".drawer > .panel__body").waitFor();
  expect(await page.evaluate(() => document.scrollingElement!.scrollHeight - document.scrollingElement!.clientHeight),
    "nothing to scroll").toBeLessThanOrEqual(0);
  await wheelOver(page, ".drawer > .panel__body");
  const m = await state(page, ".drawer > .panel__body");
  expect(m.atEnd && m.page === 0, "the drawer scrolled to its end, the page stayed").toBe(true);
});

// ADR-115 decision 2, the owner's ruling of 15 November 2026: the classification strip is always in view. The Glass's
// page under GOV.UK scrolls by the footer's height; scrolled to it, with a drawer open, the strip is still at the
// window's top and nothing paints over it.
test("under GOV.UK, scrolled to the footer, the Glass's classification strip stays at the window's top", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/keyboard/frame-harness.html?drawer=1&brand=govuk");
  await page.locator(".drawer").waitFor();
  const m = await stripAtTheEnd(page);
  expect(m.scrolled, "the page scrolled to the footer").toBe(true);
  expect(m.top, "the strip's top is the window's").toBe(0);
  expect(m.inside, "the strip is inside the window").toBe(true);
  expect(m.uncovered, "nothing paints over the strip").toEqual([true, true, true]);
});
