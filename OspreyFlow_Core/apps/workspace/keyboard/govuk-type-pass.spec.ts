// One confirming pass over every screen in the GOV.UK look (v0.6.0 #6, the owner's closed list): each harness the
// every-harness scan opens, in each of its states, under `brand=govuk`, every text element measured.
// - Its face: mono only on a value to copy, and every value to copy in mono (`.value`, `.identifier`, `td.numeric`,
//   `code`, `kbd`, `samp`, `pre`; tokens.css, DESIGN.md §9 exception 3); words everywhere else in the page's face.
// - Its size: one of the scale's sizes where it sits, read from that element's own tokens, so GOV.UK's scale on the
//   welcome, home and Admin pages (tokens.css remaps it there) and the workspace's 13px scale elsewhere
//   (DESIGN.md §9 exception 1, §11).
// GOV.UK's own header, footer, phase banner and skip link, and any element of GOV.UK Frontend's own classes
// (`govuk-*`), keep GOV.UK Frontend's sizes and are not read; nor is the harness's own chrome (`data-harness-only`).
// A gate in the keyboard suite (the orchestrator, 15 November 2026): any finding fails its page. Shown red against
// main before #6's fixes and green with them (rule 15; `process/lanes/admin/v060_i6/`). With
// `GOVUK_PASS_OUT=<file>` it also writes what it finds, one JSON line a finding; `GOVUK_PASS_LIST=1` only lists,
// failing nothing, for a list like #6's; `GOVUK_PASS_LOOK=standard` measures the standard look (no brand), for the
// record of what the one scale changes there.
import { appendFileSync, readdirSync, readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

const HERE = new URL("./", import.meta.url);
const SCAN = readFileSync(new URL("../a11y/every-harness.spec.ts", import.meta.url), "utf8");

/** every-harness's own extra states: its `EXTRA_STATES` object, read from its source and evaluated as the plain literal
 *  it is (a page's list of query strings), so every state is taken as it is written and passed as every-harness passes
 *  it, none left out for its characters. */
const LITERAL = (() => {
  const start = SCAN.indexOf("const EXTRA_STATES");
  return start < 0 ? "{}" : SCAN.slice(SCAN.indexOf("{", SCAN.indexOf("=", start)), SCAN.indexOf("\n};", start) + 2);
})();
function extraStates(): Record<string, string[]> {
  return new Function(`return (${LITERAL});`)() as Record<string, string[]>;
}

const appliesBrand = (page: string) => {
  try {
    return readFileSync(new URL(page.replace(/\.html$/, ".tsx"), HERE), "utf8").includes("applyHarnessBrand");
  } catch {
    return false;
  }
};

const EXTRA = extraStates();
const STANDARD = process.env.GOVUK_PASS_LOOK === "standard";
const PAGES = readdirSync(HERE).filter((f) => f.endsWith(".html") && appliesBrand(f)).sort();

// A misread source would make pages or states vanish rather than fail (the lane review of 15 November 2026).
test("the pass found every-harness's pages and their states", () => {
  expect(PAGES.length, "the brand-applying harness pages").toBeGreaterThan(30);
  const states = Object.values(EXTRA).flat();
  expect(Object.keys(EXTRA).length, "every-harness's pages with extra states").toBeGreaterThan(20);
  expect(states.length, "their states").toBeGreaterThan(200);
  expect(states.filter((q) => typeof q !== "string"), "each state a query string").toEqual([]);
  // Counted again a second way, from the source's own string literals (its comments aside): each is a page's name
  // or one of its states, so a state dropped on the way (a filter, a misparse) is a mismatch here.
  const code = LITERAL.split("\n").map((line) => line.replace(/^\s*\/\/.*$/, "")).join("\n");
  const strings = code.match(/"(?:[^"\\\n]|\\.)*"/g) ?? [];
  expect(Object.keys(EXTRA).length + states.length, "every string of the source, a page or a state").toBe(strings.length);
  for (const name of Object.keys(EXTRA)) expect(readdirSync(HERE), name).toContain(name);
});

for (const page of PAGES) {
  for (const state of ["", ...(EXTRA[page] ?? [])]) {
    test(`${page}${state ? ` ${state}` : ""} under GOV.UK: words in the page's face, sizes on its scale`, async ({ page: p }) => {
      await p.setViewportSize({ width: 1280, height: 900 });
      const query = [state, STANDARD ? "" : "brand=govuk"].filter(Boolean).join("&");
      await p.goto(`/keyboard/${page}${query ? `?${query}` : ""}`);  // as every-harness goes to it
      await p.waitForLoadState("networkidle").catch(() => undefined);
      await p.waitForTimeout(400);
      await p.evaluate(() => document.fonts.ready.then(() => undefined));
      // The look it claims to measure is the one drawn, and something was measured: a brand that never applied, or a
      // harness that drew nothing, never passes for want of findings.
      if (!STANDARD) await expect(p.locator("html")).toHaveAttribute("data-brand", "govuk");
      else await expect(p.locator("html")).not.toHaveAttribute("data-brand", "govuk");
      const { found, measured } = await p.evaluate(() => {
        const first = (family: string) => family.split(",")[0]!.trim().replace(/["']/g, "").toLowerCase();
        const root = getComputedStyle(document.documentElement);
        const mono = first(root.getPropertyValue("--mono"));
        const copyable = ".value, .identifier, td.numeric, code, kbd, samp, pre";
        const value = `${copyable}, .value *, .identifier *, code *, pre *`;
        // GOV.UK Frontend's own components keep GOV.UK's sizes (the orchestrator, 15 November 2026), and the harness's own
        // chrome is no screen of the product's.
        const frame = ".govuk-header, .govuk-footer, .govuk-phase-banner, .govuk-skip-link, .skip-link, [data-harness-only]";
        const govuk = (e: Element) => [...e.classList].some((c) => c.startsWith("govuk-"));
        const out: { text: string; where: string; size: number; face: string; why: string }[] = [];
        let measured = 0;
        for (const el of document.querySelectorAll("body *")) {
          const own = [...el.childNodes].filter((n) => n.nodeType === 3 && (n.textContent ?? "").trim())
            .map((n) => n.textContent!.trim()).join(" ");
          if (!own || el.closest(frame) || el.closest(".visually-hidden, .govuk-visually-hidden, script, style, svg, canvas")) continue;
          if (el.getClientRects().length === 0 || getComputedStyle(el).visibility === "hidden") continue;
          const cs = getComputedStyle(el);
          const size = parseFloat(cs.fontSize);
          const scale = [11, 12, 13, 14, 16, 19, 23, 30, 40].map((n) => parseFloat(cs.getPropertyValue(`--fs-${n}`))).filter((n) => n > 0);
          const face = first(cs.fontFamily);
          const where = `${el.tagName.toLowerCase()}${el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : ""}`;
          measured += 1;
          if (face === mono && !el.matches(value)) out.push({ text: own.slice(0, 60), where, size, face, why: "mono, not a value to copy" });
          // And the reverse (case's review of 1b0f225): a value to copy is in mono, whatever else styles it. A heading
          // classed `.value` is in the page's face by design (tokens.css), so it is not one.
          if (el.matches(copyable) && !el.matches("h1, h2, h3, h4, h5, h6") && face !== mono) out.push({ text: own.slice(0, 60), where, size, face, why: "a value to copy, not in mono" });
          // Ruling F is of sizes: GOV.UK Frontend's own classes keep GOV.UK's, so only their size is not read.
          if (!govuk(el) && !scale.includes(size)) out.push({ text: own.slice(0, 60), where, size, face, why: `${size}px, off the scale (${scale.join(", ")})` });
        }
        return { found: out, measured };
      });
      expect(measured, "text elements measured").toBeGreaterThan(0);
      const outFile = process.env.GOVUK_PASS_OUT;
      const look = STANDARD ? "standard" : "govuk";
      if (outFile) for (const f of found) appendFileSync(outFile, JSON.stringify({ look, page, state, ...f }) + "\n");
      if (process.env.GOVUK_PASS_LIST !== "1") expect(found).toEqual([]);
    });
  }
}
