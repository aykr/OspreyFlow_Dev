// @vitest-environment jsdom
// ADR-097 Amendment 3 (the owner's Part E, 13 November 2026): a heading is in the page's own face in both
// looks; mono is kept for identifiers and values (DESIGN.md §2: "Mono is semantic, not decorative"). Card
// headings ("Alerts", "Raised each week", "Team view") are `<h3 className="value">` (reports/figureParts.tsx),
// so the cascade itself is held here, with the real tokens.css, not the rule's text.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

const TOKENS = readFileSync(join(__dirname, "tokens.css"), "utf-8");

function faceOf(html: string, brand: string | null, selector = "body > *"): string {
  document.head.innerHTML = `<style>${TOKENS}</style>`;
  if (brand) document.documentElement.setAttribute("data-brand", brand);
  else document.documentElement.removeAttribute("data-brand");
  document.body.innerHTML = html;
  return getComputedStyle(document.querySelector(selector) as Element).fontFamily;
}

afterEach(() => {
  document.head.innerHTML = "";
  document.body.innerHTML = "";
  document.documentElement.removeAttribute("data-brand");
});

describe.each([["OspreyFlow", null], ["GOV.UK", "govuk"]])("in the %s look", (_look, brand) => {
  it.each(["h1", "h2", "h3", "h4", "h5", "h6"])("a %s classed as a value is in the page's face", (tag) => {
    expect(faceOf(`<${tag} class="value">Raised each week</${tag}>`, brand)).toBe("var(--ui)");
  });

  it("a value that is not a heading stays in mono", () => {
    expect(faceOf(`<span class="value">+447700900123</span>`, brand)).toBe("var(--mono)");
    expect(faceOf(`<table><tbody><tr><td class="numeric">42</td></tr></tbody></table>`, brand, "td")).toBe("var(--mono)");
  });
});
