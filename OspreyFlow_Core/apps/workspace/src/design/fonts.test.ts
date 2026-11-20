// ADR-115 E1, spec 00 §6 ("Self-host them"): the two typefaces DESIGN.md §2 names travel with the
// Glass, so a machine without them installed still draws Atkinson Hyperlegible Next and IBM Plex Mono
// — before this, `tokens.css` named both and nothing supplied either, and the Glass fell back to the
// system face. Only the weights the contract uses: 400, 600 and 700; mono 400 and 600.
//
// ADR-152 decision 6 (Amendment 2): which families and weights are used is stated once, in
// `packages/design/fonts.json`. This file reads that list and holds `fonts.ts` to it; it does not restate it.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const FONTS = readFileSync(join(__dirname, "fonts.ts"), "utf-8");
const MAIN = readFileSync(join(__dirname, "..", "main.tsx"), "utf-8");
const TOKENS = readFileSync(join(__dirname, "../../../../packages/design/tokens.css"), "utf-8");

const LIST = JSON.parse(readFileSync(join(__dirname, "../../../../packages/design/fonts.json"), "utf-8")) as {
  fonts: { family: string; role: string; source: string; weights: number[] }[];
};
// The `@fontsource` faces, in the order the list gives them: each weight of each family, as `fonts.ts` imports it.
const FONTSOURCE = LIST.fonts.filter((font) => font.source.startsWith("@fontsource/"));
const WANTED = FONTSOURCE.flatMap((font) => font.weights.map((weight) => `${font.source}/${weight}.css`));

describe("the typefaces", () => {
  it("are imported before anything is drawn, each weight the contract uses", () => {
    expect(MAIN).toMatch(/import "\.\/design\/fonts";/);
    const imported = [...FONTS.matchAll(/^import "([^"]+)";/gm)].map(([, path]) => path);
    expect(imported).toEqual(WANTED);
  });

  it("are the faces tokens.css names, every family the list names, and come from files that exist", () => {
    expect(WANTED.length).toBeGreaterThan(0);
    for (const font of LIST.fonts) expect(TOKENS).toContain(font.family);
    for (const font of FONTSOURCE) {
      for (const weight of font.weights) {
        const css = readFileSync(require.resolve(`${font.source}/${weight}.css`), "utf-8");
        // The package draws the family the list names, at the weight the list names.
        expect(/font-family:\s*'([^']+)'/.exec(css)?.[1]).toBe(font.family);
        expect(/font-weight:\s*(\d+)/.exec(css)?.[1]).toBe(String(weight));
        expect(css).toMatch(/url\(\.\/files\/[^)]+\.woff2\)/);
      }
    }
  });
});
