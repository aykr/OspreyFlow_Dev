import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { contrastRatio } from "../map/contrast";

/**
 * Home's key cap ("G", "S", "R", "A" on each place's Open button, `HomePage.tsx`): its text is the
 * button's own ink, and on the primary (brass) button it must keep 4.5:1 in every theme (WCAG 1.4.3).
 * rules-b's T3 contrast gate measured it at 4.12:1 in light and 3.92:1 under GOV.UK, because
 * `.home-key` dimmed itself with `opacity: 0.8` (CARRIES, "a hygiene step"). That gate is not on main,
 * and a jsdom test cannot see a computed colour, so this reads the two stylesheets themselves, the way
 * `design/topBarStyle.test.ts` does: the brass and ink of each theme from `tokens.css` (authoritative),
 * the key cap's opacity from `home.css`, blended as the browser draws it, over the button's rest,
 * hover and press faces.
 */

const here = dirname(fileURLToPath(import.meta.url));
const strip = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, "");
const tokens = strip(readFileSync(join(here, "..", "design", "tokens.css"), "utf8"));
const home = strip(readFileSync(join(here, "home.css"), "utf8"));

function block(css: string, selector: string): string {
  for (const [, selectors, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (selectors!.split(",").map((s) => s.trim()).includes(selector)) return body!;
  }
  throw new Error(`no rule for ${selector}`);
}

function token(body: string, name: string): string | undefined {
  return body.match(new RegExp(`--${name}\\s*:\\s*(#[0-9a-fA-F]{6})`))?.[1];
}

/** Each theme's primary-button colours: dark is `:root`'s; light and GOV.UK override it. */
const THEMES = {
  dark: block(tokens, ":root"),
  light: block(tokens, '[data-theme="light"]'),
  govuk: block(tokens, '[data-brand="govuk"]'),
} as const;

function brassOf(theme: keyof typeof THEMES, name: string): string {
  const value = token(THEMES[theme], name) ?? token(THEMES.dark, name);
  if (!value) throw new Error(`no --${name} for ${theme}`);
  return value;
}

/** The key cap's own opacity, as `home.css` sets it (1 when it sets none). */
function keyOpacity(): number {
  const value = block(home, ".home-key").match(/(?:^|;)\s*opacity\s*:\s*([\d.]+)/)?.[1];
  return value === undefined ? 1 : Number(value);
}

/** `ink` drawn at `alpha` over `under`, per sRGB channel, as the browser composites it. */
function over(ink: string, under: string, alpha: number): string {
  const channels = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
  const [a, b] = [channels(ink), channels(under)];
  return `rgb(${a.map((v, i) => Math.round(v * alpha + b[i]! * (1 - alpha))).join(", ")})`;
}

describe("Home's key cap on the primary button", () => {
  for (const theme of Object.keys(THEMES) as (keyof typeof THEMES)[]) {
    for (const face of ["brass", "brass-hover", "brass-press"]) {
      it(`keeps 4.5:1 in ${theme}, on the button's ${face} face`, () => {
        const background = brassOf(theme, face);
        const shown = over(brassOf(theme, "brass-ink"), background, keyOpacity());
        expect(contrastRatio(shown, background)).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});
