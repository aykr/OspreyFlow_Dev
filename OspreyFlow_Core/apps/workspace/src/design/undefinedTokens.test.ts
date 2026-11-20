// The font tokens the source reads are the ones `tokens.css` defines. A misspelt token
// (`--font-mono` for `--mono`) is not an error in CSS: the declaration is dropped and the browser
// falls back silently, so only a check like this finds it. Scoped to the font tokens: other reads
// of names no stylesheet defines (some with a fallback, some built up in code) are listed in the
// hand-back, not asserted here.
//
// The walk reads two roots: `apps/workspace/src`, and `packages/design`, where `primitives.css`,
// `scale.css` and `panelType.css` live since ADR-152 decision 6 (slice PL4b2). Before that move the
// walk read the three files because they were under `src/design`; a walk of `src` alone would have
// stopped reading them without any test failing.
import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const DESIGN = join(SRC, "..", "..", "..", "packages", "design");
const TOKENS = join(DESIGN, `${"tokens"}.css`);
// The roots the real check walks: the one list both the check and the reach test use.
const ROOTS = [SRC, DESIGN];
// Stems, not quoted file names: a bare quoted name in this folder reads as an old path.
const THE_THREE = ["primitives", "scale", "panelType"].map((stem) => `${stem}.css`);
const PRIMITIVES = THE_THREE[0]!;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (name === "node_modules") return [];
    if (statSync(path).isDirectory()) return files(path);
    return /\.(tsx?|css)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

/** Every font-token read in the files under `roots` that `tokensPath` does not define. */
function undefinedReads(roots: string[], tokensPath: string): string[] {
  const tokens = readFileSync(tokensPath, "utf8");
  const defined = new Set([...tokens.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)].map((m) => m[1]!));
  const missing: string[] = [];
  for (const root of roots) {
    for (const path of files(root)) {
      for (const m of readFileSync(path, "utf8").matchAll(/var\((--(?:font[a-z0-9-]*|mono|sans|serif))\b/g)) {
        if (!defined.has(m[1]!)) missing.push(`${path.slice(root.length + 1)}: ${m[1]}`);
      }
    }
  }
  return missing;
}

describe("font tokens", () => {
  it("every var(--font-…) or var(--mono) the source reads is defined in tokens.css", () => {
    const tokens = readFileSync(TOKENS, "utf8");
    expect(tokens.includes("--mono:")).toBe(true);
    expect(undefinedReads(ROOTS, TOKENS)).toEqual([]);
  });

  it("the walk reads the three stylesheets that live in packages/design", () => {
    const walked = ROOTS.flatMap(files);
    for (const name of THE_THREE) expect(walked).toContain(join(DESIGN, name));
  });

  it("a misspelt font token in a packages/design file is reported (planted in a temporary copy)", () => {
    const tmp = mkdtempSync(join(tmpdir(), "undefined-tokens-"));
    try {
      const copy = join(tmp, "design");
      cpSync(DESIGN, copy, { recursive: true, filter: (p) => !p.includes("node_modules") });
      // The shape of a real line: `font-family: var(--mono);`, misspelt, in a new file.
      writeFileSync(join(copy, "zz_planted.css"), ".planted .value { font-family: var(--font-mono); }\n");
      expect(undefinedReads([copy], TOKENS)).toEqual(["zz_planted.css: --font-mono"]);
      // And in one of the three files themselves, on the file's own line.
      const line = ".input.value, .select.value { font-family: var(--mono); }";
      const primitives = readFileSync(join(copy, PRIMITIVES), "utf8");
      expect(primitives).toContain(line);
      writeFileSync(join(copy, PRIMITIVES), primitives.replace(line, line.replace("--mono", "--font-mono")));
      expect(undefinedReads([copy], TOKENS)).toContain(`${PRIMITIVES}: --font-mono`);
    } finally {
      rmSync(tmp, { recursive: true, force: true });
    }
  });
});
