import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Seen 30 September 2026, in the running Glass: right-click a node and the radial menu drew as a
 * ring of pale grey rectangles whose labels were almost invisible. `RadialMenu` renders each
 * radial entry as a bare `<button class="radial-menu__item">`. The list layout overrides the
 * browser's button face with an inline `background: none`; the radial layout did not, and
 * `primitives.css` gave `.radial-menu__item` a text colour (`--text-primary`, near-white in the
 * dark theme) but no background. So the browser's own light button face showed through, under
 * near-white text.
 *
 * Every keyboard and live test opens the *list* layout, so nothing had ever looked at the radial
 * one. This test reads the stylesheet itself: a plain rule for the item must set a background
 * from the surface tokens, no border and the overlay shadow, so the control never depends on the browser default.
 */

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "primitives.css"),
  "utf8",
).replace(/\/\*[\s\S]*?\*\//g, ""); // comments would otherwise be glued onto the next selector

/** Declarations of every rule whose selector list names `selector` with no pseudo-class. */
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

describe("the radial menu item's own styling", () => {
  const item = plainDeclarations(".radial-menu__item");

  it("sets a background from the surface tokens, not the browser's button face", () => {
    expect(item["background"]).toMatch(/^var\(--surface-/);
  });

  it("drops the browser's border: an overlay has a shadow and no hairline (02 §5)", () => {
    expect(item["border"]).toBe("none");
    expect(item["box-shadow"]).toBe("var(--overlay-shadow)");
  });

  it("keeps its text colour from the tokens", () => {
    expect(item["color"]).toBe("var(--text-primary)");
  });
});
