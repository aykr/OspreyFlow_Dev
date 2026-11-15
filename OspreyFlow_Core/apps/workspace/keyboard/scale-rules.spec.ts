// v0.6.0 #6's one scale, held at the cascade in the browser, with the real tokens.css and primitives.css (scale.css and
// panelType.css imported first) as views-harness loads them, in the standard and GOV.UK looks:
// - a bare heading takes the scale's size for its level;
// - a heading drawn as a label stays the label's size, the page's body (the orchestrator's ruling of 15 November 2026, on case's finding), never
//   above what it labels;
// - a field classed `.value` keeps the value's mono though `.input` inherits its font (case's review of 1b0f225, M1);
// - code, keys and output are in the design's mono, never the browser's monospace.
import { expect, test } from "@playwright/test";

for (const [look, brand] of [["standard", ""], ["GOV.UK", "?brand=govuk"]] as const) {
  test(`in the ${look} look, headings, label headings, value fields and code are on the one scale`, async ({ page }) => {
    await page.goto(`/keyboard/views-harness.html${brand}`);
    await page.evaluate(() => document.fonts.ready.then(() => undefined));
    const m = await page.evaluate(() => {
      const box = document.createElement("div");
      box.innerHTML = [
        "<h1>a</h1><h2>a</h2><h3>a</h3><h4>a</h4><h5>a</h5><h6>a</h6>",
        ...["h1", "h2", "h3", "h4", "h5", "h6"].map((t) => `<${t} class="label">a</${t}>`),
        '<textarea class="input value">a</textarea><input class="input value" value="a"><select class="select value"><option>a</option></select>',
        "<code>a</code><kbd>a</kbd><samp>a</samp><pre>a</pre>",
      ].join("");
      document.body.appendChild(box);
      const root = getComputedStyle(document.body);
      const fs = (n: number) => parseFloat(root.getPropertyValue(`--fs-${n}`));
      const first = (f: string) => f.split(",")[0]!.trim().replace(/["']/g, "").toLowerCase();
      const mono = first(getComputedStyle(document.documentElement).getPropertyValue("--mono"));
      const size = (sel: string) => parseFloat(getComputedStyle(box.querySelector(sel)!).fontSize);
      const face = (sel: string) => first(getComputedStyle(box.querySelector(sel)!).fontFamily);
      return {
        bare: ["h1", "h2", "h3", "h4", "h5", "h6"].map((t) => size(`${t}:not(.label)`)),
        wanted: [fs(23), fs(19), fs(16), fs(16), fs(12), fs(12)],
        labels: ["h1", "h2", "h3", "h4", "h5", "h6"].map((t) => size(`${t}.label`)),
        body: fs(13),
        fields: ["textarea.value", "input.value", "select.value"].map(face),
        code: ["code", "kbd", "samp", "pre"].map(face),
        mono,
      };
    });
    expect.soft(m.bare, "a bare heading's size for its level").toEqual(m.wanted);
    expect.soft(m.labels, "a label heading at the body's size").toEqual(m.labels.map(() => m.body));
    expect.soft(m.fields, "a field classed .value in mono").toEqual([m.mono, m.mono, m.mono]);
    expect.soft(m.code, "code, keys and output in the design's mono").toEqual([m.mono, m.mono, m.mono, m.mono]);
  });
}
