// ADR-115 E1, spec 00 §6 ("Self-host them"): the two typefaces DESIGN.md §2 names travel with the
// Glass, so a machine without them installed still draws Atkinson Hyperlegible Next and IBM Plex Mono
// — before this, `tokens.css` named both and nothing supplied either, and the Glass fell back to the
// system face. Only the weights the contract uses: 400, 600 and 700; mono 400 and 600.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const FONTS = readFileSync(join(__dirname, "fonts.ts"), "utf-8");
const MAIN = readFileSync(join(__dirname, "..", "main.tsx"), "utf-8");
const TOKENS = readFileSync(join(__dirname, "tokens.css"), "utf-8");

const WANTED = [
  "@fontsource/atkinson-hyperlegible-next/400.css",
  "@fontsource/atkinson-hyperlegible-next/600.css",
  "@fontsource/atkinson-hyperlegible-next/700.css",
  "@fontsource/ibm-plex-mono/400.css",
  "@fontsource/ibm-plex-mono/600.css",
];

describe("the typefaces", () => {
  it("are imported before anything is drawn, each weight the contract uses", () => {
    expect(MAIN).toMatch(/import "\.\/design\/fonts";/);
    const imported = [...FONTS.matchAll(/^import "([^"]+)";/gm)].map(([, path]) => path);
    expect(imported).toEqual(WANTED);
  });

  it("are the faces tokens.css names, and come from files that exist", () => {
    for (const path of WANTED) {
      const css = readFileSync(require.resolve(path), "utf-8");
      const family = /font-family:\s*'([^']+)'/.exec(css)?.[1];
      expect(TOKENS).toContain(`'${family}'`);
      expect(css).toMatch(/url\(\.\/files\/[^)]+\.woff2\)/);
    }
  });
});
