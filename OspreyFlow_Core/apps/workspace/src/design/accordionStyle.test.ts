// ADR-115 E6 (review item 14; the reference's Query rows): an accordion row is no box — a hairline
// divides the rows — its chevron on the left and its title at 13px 600, 36px tall.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const CSS = readFileSync(join(__dirname, "primitives.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");
const rule = (selector: string) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const body = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, "m").exec(CSS)?.[1] ?? "";
  return Object.fromEntries(body.split(";").map((d) => d.split(":").map((x) => x.trim())).filter(([k, v]) => k && v));
};

describe("an accordion row", () => {
  it("is divided by a hairline, not boxed", () => {
    const section = rule(".accordion-section");
    expect(section.border).toBeUndefined();
    expect(section["border-bottom"]).toBe("1px solid var(--border-subtle)");
  });

  it("titles itself at 13px 600 in a 36px row", () => {
    const header = rule(".accordion-section__header");
    expect(header["font-size"]).toBe("var(--fs-13)");
    expect(header["font-weight"]).toBe("600");
    expect(header["min-height"]).toBe("var(--h-control-36)");
  });
});
