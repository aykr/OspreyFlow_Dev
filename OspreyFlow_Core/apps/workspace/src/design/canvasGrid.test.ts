// ADR-097 step 2 (design review item 10, DESIGN.md §9 exception 4): the graph canvas, and no other
// surface, gets a measurement grid: 1px lines in `--border-subtle` on an 8px lattice.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(__dirname, "primitives.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");

function gridRules(css: string): { selector: string; body: string }[] {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, , body]) => /background-image:[^;]*linear-gradient/.test(body ?? ""))
    .map(([, selector, body]) => ({ selector: (selector ?? "").trim(), body: body ?? "" }));
}

describe("the canvas grid", () => {
  it("is on the network canvas only, 1px border-subtle lines every 8px", () => {
    const rules = gridRules(CSS);
    expect(rules.map((r) => r.selector)).toEqual([".network-canvas"]);
    expect(rules[0]!.body).toMatch(/var\(--border-subtle\) 1px/);
    expect(rules[0]!.body).toMatch(/background-size:\s*8px 8px/);
  });

  it("the check finds a grid on another surface", () => {
    const planted = ".panel { background-image: linear-gradient(var(--border-subtle) 1px, transparent 1px); }";
    expect(gridRules(planted).map((r) => r.selector)).toEqual([".panel"]);
  });
});
