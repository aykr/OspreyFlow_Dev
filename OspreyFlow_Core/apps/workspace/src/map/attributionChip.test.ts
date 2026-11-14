import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import { contrastRatio } from "./contrast";

/**
 * The map's attribution chip (`MapView.tsx`, CARRIES row 91): its words sat on a translucent
 * `rgba(0,0,0,0.4)` over the map's canvas, so their contrast depended on whatever the map drew beneath
 * and could not be measured in any theme (rules-b's T3 gate listed it as unmeasurable). It now stands on
 * an opaque token surface. A jsdom render cannot compute a colour, and nothing renders MapView here, so
 * this reads the chip's own style from the source and each theme's tokens from `tokens.css`
 * (authoritative), as `home/homeKey.test.ts` does. The browser-side measure is every-harness's
 * map-view scans, whose listed findings come off with this change.
 */

const here = dirname(fileURLToPath(import.meta.url));
const strip = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, "");
const tokens = strip(readFileSync(join(here, "..", "design", "tokens.css"), "utf8"));
const mapView = readFileSync(join(here, "MapView.tsx"), "utf8");

function declared(selector: string): Record<string, string> {
  for (const [, selectors, body] of tokens.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (selectors!.split(",").map((s) => s.trim()).includes(selector)) {
      return Object.fromEntries([...body!.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(([, k, v]) => [k!, v!.trim()]));
    }
  }
  throw new Error(`no rule for ${selector}`);
}

const dark = declared(":root");
const light = { ...dark, ...declared('[data-theme="light"]') };
const THEMES = { dark, light, govuk: { ...light, ...declared('[data-brand="govuk"]') } };

function resolve(value: string, theme: Record<string, string>, depth = 0): string {
  const ref = /^var\((--[\w-]+)\)$/.exec(value.trim());
  if (!ref) return value.trim();
  const next = theme[ref[1]!];
  if (next === undefined || depth > 5) throw new Error(`${ref[1]} is not a token`);
  return resolve(next, theme, depth + 1);
}

/** The chip's own style object: the inline style of the element that holds `{active.attribution}`. */
function chipStyle(): Record<string, string> {
  const at = mapView.indexOf("{active.attribution}");
  const style = mapView.slice(mapView.lastIndexOf("style={{", at), at);
  return Object.fromEntries([...style.matchAll(/(\w+):\s*"([^"]*)"/g)].map(([, k, v]) => [k!, v!]));
}

describe("the map's attribution chip is measurable and passes in every theme (CARRIES 91)", () => {
  test("its background is a token, not a raw colour laid over the map", () => {
    expect(chipStyle().background).toMatch(/^var\(--[\w-]+\)$/);
  });

  test.each(Object.keys(THEMES) as (keyof typeof THEMES)[])("%s: an opaque surface, its words at 4.5:1 or better", (name) => {
    const theme = THEMES[name];
    const { background, color } = chipStyle();
    const surface = resolve(background!, theme);
    const ink = resolve(color!, theme);
    expect(surface, "an opaque colour, so nothing beneath it is seen").toMatch(/^#[0-9a-fA-F]{6}$/);
    expect(contrastRatio(ink, surface)).toBeGreaterThanOrEqual(4.5);
  });
});
