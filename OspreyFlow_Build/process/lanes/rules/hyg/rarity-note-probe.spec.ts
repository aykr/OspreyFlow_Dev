// rules-hyg item 2, a one-off probe (not a gate): what axe sees when it reads the metrics panel's
// rarity note as partly obscured. The page is loaded exactly as every-harness.spec.ts loads it; the
// record is axe's own color-contrast "incomplete" data for the note, and the geometry around it.
import AxeBuilder from "@axe-core/playwright";
import { test } from "@playwright/test";

const NOTE = "Filters dim, they never remove";

for (const variant of ["dark", "light", "govuk"] as const) {
  test(`rarity note (${variant})`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    const query = ["filter=rarity", variant === "govuk" ? "brand=govuk" : ""].filter(Boolean).join("&");
    await page.goto(`/keyboard/metrics-panel-harness.html?${query}`);
    await page.waitForLoadState("networkidle");
    await page.evaluate(() => document.fonts.ready);
    if (variant === "light") {
      await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
    }
    const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
    const mine = results.incomplete
      .flatMap((r) => r.nodes)
      .filter((n) => JSON.stringify(n).includes(NOTE));
    const violated = results.violations
      .flatMap((r) => r.nodes)
      .filter((n) => JSON.stringify(n).includes(NOTE));
    const geometry = await page.evaluate((note) => {
      const p = [...document.querySelectorAll("p")].find((e) => e.textContent?.includes(note));
      if (!p) return { found: false };
      const box = p.getBoundingClientRect();
      const clippers: { tag: string; cls: string; overflow: string; box: number[] }[] = [];
      for (let e = p.parentElement; e; e = e.parentElement) {
        const s = getComputedStyle(e);
        if (s.overflow !== "visible" || s.overflowY !== "visible") {
          const b = e.getBoundingClientRect();
          clippers.push({ tag: e.tagName, cls: e.className, overflow: `${s.overflowX}/${s.overflowY}`, box: [b.top, b.bottom] });
        }
      }
      // What is on top at points across the note's box (rows, at its left, centre and right).
      const atPoints: string[] = [];
      for (const fy of [0.1, 0.5, 0.9]) {
        for (const fx of [0.05, 0.5, 0.95]) {
          const x = box.left + box.width * fx, y = box.top + box.height * fy;
          const top = document.elementFromPoint(x, y);
          atPoints.push(`${fx},${fy}: ${top === p || p.contains(top) ? "the note" : top ? `${top.tagName}.${top.className}` : "nothing (outside the viewport)"}`);
        }
      }
      // Every element whose box meets the note's, other than its own ancestors and descendants:
      // what axe's elmPartiallyObscuring ("partially overlaps other elements") is about.
      const overlapping = [...document.querySelectorAll("body *")]
        .filter((e) => e !== p && !e.contains(p) && !p.contains(e))
        .map((e) => ({ e, b: e.getBoundingClientRect() }))
        .filter(({ b }) => b.width > 0 && b.height > 0 && b.left < box.right && b.right > box.left && b.top < box.bottom && b.bottom > box.top)
        .map(({ e, b }) => `${e.tagName}.${e.className} [${b.top.toFixed(1)},${b.bottom.toFixed(1)}] ${(e.textContent ?? "").trim().slice(0, 30)}`);
      const stacks = [0.1, 0.9].map((fy) =>
        document.elementsFromPoint(box.left + box.width / 2, box.top + box.height * fy).map((e) => `${e.tagName}.${e.className}${e.contains(p) || e === p ? "" : " (NOT an ancestor)"}`).join(" > "),
      );
      const range = document.createRange();
      range.selectNodeContents(p);
      const lines = [...range.getClientRects()].map((r) => `[${r.top.toFixed(1)},${r.bottom.toFixed(1)}] x[${r.left.toFixed(1)},${r.right.toFixed(1)}]`);
      return {
        lines,
        overlapping,
        stacks,
        found: true,
        box: [box.top, box.bottom, box.left, box.right],
        viewport: [window.innerWidth, window.innerHeight],
        clippers,
        atPoints,
      };
    }, NOTE);
    console.log(
      `PROBE ${variant}: ` +
        JSON.stringify({
          incomplete: mine.map((n) => ({ target: n.target, any: n.any.map((c) => ({ id: c.id, message: c.message, data: c.data, related: c.relatedNodes.map((r) => r.target) })) })),
          violations: violated.map((n) => n.target),
          geometry,
        }),
    );
  });
}
