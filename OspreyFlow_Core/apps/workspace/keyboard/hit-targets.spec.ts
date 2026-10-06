// Every control the Glass draws is at least 24 by 24 pixels (ADR-097 step 3; WCAG 2.2's minimum target
// size, `02_GLASS_FRONTEND.md` §6). Read from the laid-out page in each harness, so a control a style
// shrank is found wherever it is.
import { expect, test } from "@playwright/test";

const HARNESSES = [
  "/keyboard/harness.html",
  "/keyboard/top-bar-harness.html",
  "/keyboard/panel-frames-harness.html",
  "/keyboard/inspector-harness.html",
  "/keyboard/metrics-panel-harness.html",
  "/keyboard/query-builder-harness.html",
  "/keyboard/timeline-playback-harness.html",
];

for (const url of HARNESSES) {
  test(`every visible control is at least 24 by 24 pixels: ${url}`, async ({ page }) => {
    await page.goto(url);
    await page.waitForTimeout(800);
    const small = await page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>("button, select, input:not([type=hidden]), [role=button], [role=tab], a[href]"))
        .filter((el) => {
          const r = el.getBoundingClientRect();
          const style = getComputedStyle(el);
          // A harness's own scaffolding (a Tab sentinel, a stand-in for another panel) is not the Glass.
          if (el.hasAttribute("data-harness-only")) return false;
          return r.width > 0 && r.height > 0 && style.visibility !== "hidden" && !el.closest("[hidden]");
        })
        .map((el) => {
          const r = el.getBoundingClientRect();
          return { name: el.getAttribute("aria-label") ?? el.textContent?.trim().slice(0, 30) ?? el.tagName, w: Math.round(r.width), h: Math.round(r.height), cls: el.className };
        })
        .filter((c) => c.w < 24 || c.h < 24),
    );
    expect(small).toEqual([]);
  });
}
