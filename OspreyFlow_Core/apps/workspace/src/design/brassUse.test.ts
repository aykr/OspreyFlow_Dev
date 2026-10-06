// ADR-097 step 1 (design review item 5, DESIGN.md §3.2): brass means the primary action, focus and
// the selection stroke. It is not a "current" state, a toggle's on, a tab, a data bar or a slider at
// rest. This reads the primitives and fails on brass in any rule outside that set.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(__dirname, "primitives.css"), "utf-8");

/** Rules allowed to use brass: the primary button tier and focus. */
const ALLOWED = [/^\.btn--primary(:hover|:active)?$/, /:focus-visible/, /:focus\b/];

function brassRules(css: string): string[] {
  const rules: string[] = [];
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const match of stripped.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const [, selectors, body] = match;
    if (!/var\(--brass/.test(body ?? "")) continue;
    for (const selector of (selectors ?? "").split(",").map((s) => s.trim())) {
      if (!ALLOWED.some((re) => re.test(selector))) rules.push(selector);
    }
  }
  return rules;
}

describe("brass in the primitives", () => {
  it("is only on the primary action and focus", () => {
    expect(brassRules(CSS)).toEqual([]);
  });

  it("the check finds brass on a current state, as it was before ADR-097", () => {
    expect(brassRules('.tabs__tab[aria-selected="true"] { border-bottom-color: var(--brass); }')).toEqual([
      '.tabs__tab[aria-selected="true"]',
    ]);
  });
});
