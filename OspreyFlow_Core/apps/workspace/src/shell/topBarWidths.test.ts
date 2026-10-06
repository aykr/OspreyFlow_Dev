// ADR-097 step 3 (design review item 15): the case switcher and search keep room enough to read, and a
// visually hidden span exists for words a screen reader needs but the bar does not show.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(__dirname, "../design/primitives.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");
const rule = (selector: string) =>
  [...CSS.matchAll(/([^{}]+)\{([^{}]*)\}/g)].find(([, sel]) => sel!.split(",").map((x) => x.trim()).includes(selector))?.[2] ?? "";

describe("the top bar's widths", () => {
  it("gives the case switcher at least 240px and search at least 280px", () => {
    expect(rule(".menu-button--case")).toMatch(/min-width:\s*240px/);
    expect(rule(".global-search")).toMatch(/min-width:\s*280px/);
  });

  it("has a visually hidden class that keeps text for assistive technology", () => {
    expect(rule(".visually-hidden")).toMatch(/clip-path|clip:/);
    expect(rule(".visually-hidden")).toMatch(/position:\s*absolute/);
  });
});
