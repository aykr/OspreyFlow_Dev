// One confirming pass over every screen in the GOV.UK look (v0.6.0 #6, the owner's closed list): each harness the
// every-harness scan opens, in each of its states, under `brand=govuk`, every text element measured.
// - Its face: mono only on a value to copy (`.value`, `.identifier`, `td.numeric`, `code`, `kbd`, `samp`, `pre`;
//   tokens.css, DESIGN.md §9 exception 3); words everywhere else in the page's face.
// - Its size: one of the scale's sizes where it sits, read from that element's own tokens, so GOV.UK's scale on the
//   welcome, home and Admin pages (tokens.css remaps it there) and the workspace's 13px scale elsewhere
//   (DESIGN.md §9 exception 1, §11).
// GOV.UK's own header, footer, phase banner and skip link keep GOV.UK Frontend's sizes, and are not read.
// With `GOVUK_PASS_OUT=<file>` it writes what it finds, one JSON line a finding, for the list; with
// `GOVUK_PASS_STRICT=1` any finding fails its page. With neither it is skipped: until the list's fixes are in, it
// has no green to keep and is not a gate (rule 15), so it costs the keyboard suite nothing.
import { appendFileSync, readdirSync, readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

const HERE = new URL("./", import.meta.url);
const SCAN = readFileSync(new URL("../a11y/every-harness.spec.ts", import.meta.url), "utf8");

/** every-harness's own extra states, read from its source: a page's list of query strings. */
function extraStates(): Record<string, string[]> {
  const block = SCAN.slice(SCAN.indexOf("const EXTRA_STATES"), SCAN.indexOf("\n};", SCAN.indexOf("const EXTRA_STATES")));
  const out: Record<string, string[]> = {};
  for (const m of block.matchAll(/"([\w-]+\.html)":\s*\[([\s\S]*?)\]/g)) {
    out[m[1]!] = [...m[2]!.matchAll(/"([^"\n]*)"/g)].map((q) => q[1]!).filter((q) => /^[\w=&%,.:#-]*$/.test(q));
  }
  return out;
}

const appliesBrand = (page: string) => {
  try {
    return readFileSync(new URL(page.replace(/\.html$/, ".tsx"), HERE), "utf8").includes("applyHarnessBrand");
  } catch {
    return false;
  }
};

test.skip(!process.env.GOVUK_PASS_OUT && process.env.GOVUK_PASS_STRICT !== "1", "the confirming pass runs on asking");

const EXTRA = extraStates();
const PAGES = readdirSync(HERE).filter((f) => f.endsWith(".html") && appliesBrand(f)).sort();

for (const page of PAGES) {
  for (const state of ["", ...(EXTRA[page] ?? [])]) {
    test(`${page}${state ? ` ${state}` : ""} under GOV.UK: words in the page's face, sizes on its scale`, async ({ page: p }) => {
      await p.setViewportSize({ width: 1280, height: 900 });
      const [query, hash] = state.split("#");
      await p.goto(`/keyboard/${page}?${[query, "brand=govuk"].filter(Boolean).join("&")}${hash ? `#${hash}` : ""}`);
      await p.waitForLoadState("networkidle").catch(() => undefined);
      await p.waitForTimeout(400);
      await p.evaluate(() => document.fonts.ready.then(() => undefined));
      const found = await p.evaluate(() => {
        const first = (family: string) => family.split(",")[0]!.trim().replace(/["']/g, "").toLowerCase();
        const root = getComputedStyle(document.documentElement);
        const mono = first(root.getPropertyValue("--mono"));
        const value = ".value, .identifier, td.numeric, code, kbd, samp, pre, .value *, .identifier *, code *, pre *";
        const frame = ".govuk-header, .govuk-footer, .govuk-phase-banner, .govuk-skip-link, .skip-link";
        const out: { text: string; where: string; size: number; face: string; why: string }[] = [];
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
          if (face === mono && !el.matches(value)) out.push({ text: own.slice(0, 60), where, size, face, why: "mono, not a value to copy" });
          if (!scale.includes(size)) out.push({ text: own.slice(0, 60), where, size, face, why: `${size}px, off the scale (${scale.join(", ")})` });
        }
        return out;
      });
      const outFile = process.env.GOVUK_PASS_OUT;
      if (outFile) for (const f of found) appendFileSync(outFile, JSON.stringify({ page, state, ...f }) + "\n");
      if (process.env.GOVUK_PASS_STRICT === "1") expect(found).toEqual([]);
    });
  }
}
