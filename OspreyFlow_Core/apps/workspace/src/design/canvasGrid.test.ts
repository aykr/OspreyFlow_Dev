// ADR-097 step 2 (design review item 10, DESIGN.md §9 exception 4): the graph canvas, and no other
// surface, gets a measurement grid: 1px lines in `--border-subtle` on an 8px lattice. DESIGN.md v0.3
// (ADR-115 decision 9): a 16px lattice, its lines `--border-subtle` mixed to 40% toward transparent.
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
  it("is on the network canvas only, 1px lines of border-subtle at 40% every 16px", () => {
    const rules = gridRules(CSS);
    expect(rules.map((r) => r.selector)).toEqual([".network-canvas"]);
    expect(rules[0]!.body).toMatch(/var\(--grid-line\) 1px/);
    expect(rules[0]!.body).toMatch(/background-size:\s*16px 16px/);
    const tokens = readFileSync(join(__dirname, "tokens.css"), "utf-8");
    expect(tokens).toMatch(/--grid-line:\s*color-mix\(in oklab, var\(--border-subtle\) 40%, transparent\);/);
  });

  it("the check finds a grid on another surface", () => {
    const planted = ".panel { background-image: linear-gradient(var(--border-subtle) 1px, transparent 1px); }";
    expect(gridRules(planted).map((r) => r.selector)).toEqual([".panel"]);
  });
});
