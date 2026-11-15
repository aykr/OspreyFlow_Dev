// One confirming pass over every screen in the GOV.UK look (v0.6.0 #6, the owner's closed list): each harness the
// every-harness scan opens, in each of its states, under `brand=govuk`, every text element measured.
// - Its face: mono only on a value to copy (`.value`, `.identifier`, `td.numeric`, `code`, `kbd`, `samp`, `pre`;
//   tokens.css, DESIGN.md §9 exception 3); words everywhere else in the page's face.
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

const EXTRA = extraStates();
const STANDARD = process.env.GOVUK_PASS_LOOK === "standard";
const PAGES = readdirSync(HERE).filter((f) => f.endsWith(".html") && appliesBrand(f)).sort();

for (const page of PAGES) {
  for (const state of ["", ...(EXTRA[page] ?? [])]) {
    test(`${page}${state ? ` ${state}` : ""} under GOV.UK: words in the page's face, sizes on its scale`, async ({ page: p }) => {
      await p.setViewportSize({ width: 1280, height: 900 });
      const [query, hash] = state.split("#");
      const brand = STANDARD ? "" : "brand=govuk";
      await p.goto(`/keyboard/${page}?${[query, brand].filter(Boolean).join("&")}${hash ? `#${hash}` : ""}`);
      await p.waitForLoadState("networkidle").catch(() => undefined);
      await p.waitForTimeout(400);
      await p.evaluate(() => document.fonts.ready.then(() => undefined));
      const found = await p.evaluate(() => {
        const first = (family: string) => family.split(",")[0]!.trim().replace(/["']/g, "").toLowerCase();
        const root = getComputedStyle(document.documentElement);
        const mono = first(root.getPropertyValue("--mono"));
        const value = ".value, .identifier, td.numeric, code, kbd, samp, pre, .value *, .identifier *, code *, pre *";
        // GOV.UK Frontend's own components keep GOV.UK's sizes (the orchestrator, 15 November 2026), and the harness's own
        // chrome is no screen of the product's.
        const frame = ".govuk-header, .govuk-footer, .govuk-phase-banner, .govuk-skip-link, .skip-link, [data-harness-only]";
        const govuk = (e: Element) => [...e.classList].some((c) => c.startsWith("govuk-"));
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
          if (govuk(el)) continue;
          if (face === mono && !el.matches(value)) out.push({ text: own.slice(0, 60), where, size, face, why: "mono, not a value to copy" });
          if (!scale.includes(size)) out.push({ text: own.slice(0, 60), where, size, face, why: `${size}px, off the scale (${scale.join(", ")})` });
        }
        return out;
      });
      const outFile = process.env.GOVUK_PASS_OUT;
      const look = STANDARD ? "standard" : "govuk";
      if (outFile) for (const f of found) appendFileSync(outFile, JSON.stringify({ look, page, state, ...f }) + "\n");
      if (process.env.GOVUK_PASS_LIST !== "1") expect(found).toEqual([]);
    });
  }
}
