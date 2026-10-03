import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Seen 3 October 2026 in the running Glass: the case choice was a bare white box, Filters dropped
 * below the search box, and Export and Sign out broke over two lines. Two causes were in the
 * stylesheet. `.select { composes: input; }` is CSS-modules syntax; in a plain stylesheet it does
 * nothing, so every `<Select>` was drawn with the browser's own white face. And the search box's
 * Filters button and the header's buttons had no rules at all. This reads the stylesheet itself,
 * the way `radialMenuStyle.test.ts` does, because a jsdom test cannot see a missing rule.
 */

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "primitives.css"),
  "utf8",
).replace(/\/\*[\s\S]*?\*\//g, "");

function plainDeclarations(selector: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [, selectors, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const names = selectors!.split(",").map((s) => s.trim());
    if (!names.includes(selector)) continue;
    for (const decl of body!.split(";")) {
      const at = decl.indexOf(":");
      if (at < 0) continue;
      out[decl.slice(0, at).trim()] = decl.slice(at + 1).trim();
    }
  }
  return out;
}

describe("controls that were drawn with the browser's own face", () => {
  it("a select has a dark surface and a border of its own, not a `composes` that does nothing here", () => {
    expect(css).not.toMatch(/composes\s*:/);
    const select = plainDeclarations(".select");
    expect(select["background"]).toMatch(/var\(--surface/);
    expect(select["border"]).toMatch(/var\(--border/);
    expect(select["color"]).toMatch(/var\(--text-primary/);
  });
});

describe("the top bar", () => {
  it("keeps a button's label on one line", () => {
    expect(plainDeclarations(".app-header .btn")["white-space"]).toBe("nowrap");
  });

  it("lets whole items wrap to a second line rather than breaking inside one", () => {
    expect(plainDeclarations(".app-header")["flex-wrap"]).toBe("wrap");
  });

  it("puts the Filters button inside the search box, at its right-hand end", () => {
    expect(plainDeclarations(".global-search__field")["position"]).toBe("relative");
    expect(plainDeclarations(".global-search__filters")["position"]).toBe("absolute");
    expect(plainDeclarations(".global-search__filters")["right"]).toBeTruthy();
  });
});

describe("telling the two apps apart (owner, 3 October 2026)", () => {
  it("draws the open app filled in brass in the switch, and the other plain", () => {
    expect(css).toMatch(/\.app-switcher \.btn\[aria-pressed="true"\]/);
    expect(plainDeclarations(".app-switcher")["border"]).toMatch(/var\(--brass/);
  });

  it("puts a brass line under the bar while the Ingest Studio is open", () => {
    const rule = css.match(/\.app-header\[data-app="ingest"\]\s*\{([^}]*)\}/);
    expect(rule).not.toBeNull();
    expect(rule![1]).toMatch(/border-bottom:[^;]*var\(--brass/);
  });

  it("pushes the account to the right-hand end", () => {
    expect(plainDeclarations(".app-header__account")["margin-left"]).toBe("auto");
  });
});

describe("the account button", () => {
  it("lets the user name be cut short but never the clearance beside it", () => {
    expect(plainDeclarations(".menu-button__name")["text-overflow"]).toBe("ellipsis");
    expect(plainDeclarations(".menu-button__fixed")["flex"]).toBe("none");
  });
});

describe("the dropdown panel", () => {
  it("floats over what is below it on a raised surface, and is not clipped to its button", () => {
    const panel = plainDeclarations(".menu-panel");
    expect(panel["position"]).toBe("absolute");
    expect(panel["background"]).toMatch(/var\(--surface/);
    expect(panel["box-shadow"]).toMatch(/var\(--overlay-shadow/);
    expect(Number(panel["z-index"])).toBeGreaterThanOrEqual(30);
  });

  it("keeps a long case name on one line with an ellipsis", () => {
    const label = plainDeclarations(".menu-button__label");
    expect(label["overflow"]).toBe("hidden");
    expect(label["text-overflow"]).toBe("ellipsis");
    expect(label["white-space"]).toBe("nowrap");
  });
});
